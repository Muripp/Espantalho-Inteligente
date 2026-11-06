// Receptor VIGIA: simulação padrão; perfil VIGIA_SERVOS para dois SG90.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <cstring>
#include <initializer_list>

constexpr char NO[] = "torre1";
#ifdef VIGIA_SERVOS
constexpr char VERSAO_FW[] = "vigia-servos-1.2.0";
constexpr bool SIMULADO = false;
constexpr char MODO[] = "servos";
#else
constexpr char VERSAO_FW[] = "vigia-receptor-1.0.0";
constexpr bool SIMULADO = true;
constexpr char MODO[] = "simulacao";
#endif
constexpr size_t MAX_LINHA = 1024;
char linha[MAX_LINHA];
size_t usados = 0;
bool descartando = false;
bool sincronizado = false;
int64_t diferenca = 0;
uint32_t ultimoStatus = 0;
uint32_t ultimaEntrada = 0;
uint32_t recebidos = 0;
String vistos[20];  // deduplicação apenas enquanto a placa permanece ligada
size_t proximoVisto = 0;

int64_t agora() { return esp_timer_get_time() / 1000 + diferenca; }

void envelope(JsonDocument &doc, const char *tipo) {
  doc["tipo"] = tipo;
  doc["v"] = 1;
  doc["no"] = NO;
  doc["ts"] = agora();
}

void transmitir(JsonDocument &doc) {
  serializeJson(doc, Serial);
  Serial.write('\n');
}

void ack(const char *id, const char *status, const char *erro = nullptr,
         bool repetido = false) {
  JsonDocument doc;
  envelope(doc, "ack");
  doc["dados"]["evento"] = id;
  doc["dados"]["status"] = status;
  doc["dados"]["simulado"] = SIMULADO;
  if (erro) doc["dados"]["erro"] = erro;
  if (repetido) doc["dados"]["repetido"] = true;
  transmitir(doc);
}

void status() {
  JsonDocument doc;
  envelope(doc, "status");
  doc["dados"]["firmware"] = VERSAO_FW;
  doc["dados"]["uptime_s"] = esp_timer_get_time() / 1000000;
  doc["dados"]["modo"] = MODO;
  doc["dados"]["relogio_sincronizado"] = sincronizado;
  doc["dados"]["eventos_recebidos"] = recebidos;
  transmitir(doc);
}

void capacidades() {
  JsonDocument doc;
  envelope(doc, "capacidades");
  doc["dados"]["firmware"] = VERSAO_FW;
  doc["dados"]["modo"] = MODO;
  doc["dados"]["atuadores_habilitados"] = !SIMULADO;
#ifdef VIGIA_SERVOS
  doc["dados"]["acoes"].to<JsonArray>().add("servo");
  JsonArray pinos = doc["dados"]["pinos_servo"].to<JsonArray>();
  pinos.add(25); pinos.add(26);
#else
  doc["dados"]["acoes"].to<JsonArray>();
  JsonArray simuladas = doc["dados"]["acoes_simuladas"].to<JsonArray>();
  for (const char *a : {"som", "led", "rele", "servo", "parar"}) simuladas.add(a);
#endif
  transmitir(doc);
}

#ifdef VIGIA_SERVOS
#include "servos.h"
#endif

bool acaoConhecida(const char *a) {
#ifdef VIGIA_SERVOS
  return !strcmp(a, "servo");
#else
  return !strcmp(a, "som") || !strcmp(a, "led") || !strcmp(a, "rele") ||
         !strcmp(a, "servo") || !strcmp(a, "parar");
#endif
}

void processar(const char *texto) {
  JsonDocument doc;
  if (deserializeJson(doc, texto, DeserializationOption::NestingLimit(8))) {
    Serial.println("# JSON invalido");
    return;
  }
  if (!doc.is<JsonObject>() || !doc["tipo"].is<const char *>()) return;
  const char *tipo = doc["tipo"];
  if (!doc["v"].is<int>() || doc["v"].as<int>() != 1) return;
  if (!strcmp(tipo, "hora")) {
    if (!doc["ts"].is<int64_t>() || doc["ts"].as<int64_t>() <= 0) return;
    diferenca = doc["ts"].as<int64_t>() - esp_timer_get_time() / 1000;
    sincronizado = true;
    status();
    return;
  }
  if (!strcmp(tipo, "consulta")) { capacidades(); status(); return; }
  if (strcmp(tipo, "evento")) return;
  const char *id = doc["id"] | "";
  if (!*id || strlen(id) > 64) return;
#ifdef VIGIA_SERVOS
  if (movimentoAtivo && eventoAtivo == id) { ack(id, "recebido", nullptr, true); return; }
#endif
  for (const String &visto : vistos) {
    if (visto == id) { ack(id, "executado", nullptr, true); return; }
  }
  if (!sincronizado) { ack(id, "erro", "relogio_nao_sincronizado"); return; }
  if (!doc["ts"].is<int64_t>() || !doc["validade_ms"].is<int>() ||
      doc["validade_ms"].as<int>() <= 0 || doc["validade_ms"].as<int>() > 10000) {
    ack(id, "erro", "tempo_invalido"); return;
  }
  const int64_t atraso = agora() - doc["ts"].as<int64_t>();
  if (atraso < -1000 || atraso > doc["validade_ms"].as<int>()) {
    ack(id, "erro", "expirado_ou_futuro"); return;
  }
  if (!doc["animal"].is<const char *>() || !doc["resposta"].is<const char *>() ||
      !doc["confianca"].is<double>() || doc["confianca"].as<double>() < 0 ||
      doc["confianca"].as<double>() > 1 || !doc["acoes"].is<JsonArray>() ||
      doc["acoes"].size() == 0 || doc["acoes"].size() > 16) {
    ack(id, "erro", "evento_invalido"); return;
  }
  if (!strcmp(doc["animal"].as<const char *>(), "pessoa")) {
    ack(id, "erro", "presenca_humana"); return;
  }
  for (JsonObjectConst a : doc["acoes"].as<JsonArrayConst>()) {
    const char *destino = a["esp32"] | "";
    const char *acao = a["acao"] | "";
    if (strcmp(destino, NO) || !acaoConhecida(acao) || !a["params"].is<JsonObjectConst>()) {
      ack(id, "erro", "acao_ou_destino_invalido"); return;
    }
  }
#ifdef VIGIA_SERVOS
  if (movimentoAtivo) { ack(id, "erro", "servos_ocupados"); return; }
  if (!validarServos(doc["acoes"].as<JsonArrayConst>())) {
    ack(id, "erro", "parametros_servo_invalidos"); return;
  }
  ++recebidos;
  ack(id, "recebido");
  iniciarServos(id, doc["acoes"].as<JsonArrayConst>());
#else
  // Perfil original de simulação.
  vistos[proximoVisto] = id;
  proximoVisto = (proximoVisto + 1) % 20;
  ++recebidos;
  ack(id, "recebido");
  Serial.printf("# SIMULADO: animal=%s confianca=%.2f resposta=%s\n",
                doc["animal"].as<const char *>(), doc["confianca"].as<double>(),
                doc["resposta"].as<const char *>());
  ack(id, "executado"); // executado significa SIMULADO neste perfil
#endif
}

void setup() {
  Serial.begin(115200);
  capacidades();
  status();
  ultimoStatus = millis();
}

void loop() {
#ifdef VIGIA_SERVOS
  atualizarServos();
#endif
  // Limitar bytes por ciclo permite atender heartbeat e watchdog sob tráfego.
  for (size_t n = 0; n < 256 && Serial.available(); ++n) {
    const char c = Serial.read();
    ultimaEntrada = millis();
    if (c == '\n') {
      if (!descartando && usados) { linha[usados] = '\0'; processar(linha); }
      usados = 0;
      descartando = false;
    } else if (!descartando) {
      if (c == '\0' || usados >= MAX_LINHA - 1) {
        descartando = true;
        usados = 0;
        Serial.println("# Linha invalida ou longa demais; descartando ate newline");
      } else linha[usados++] = c;
    }
  }
  if (usados && uint32_t(millis() - ultimaEntrada) > 2000) {
    usados = 0;
    descartando = true; // não interpretar sufixo de uma mensagem interrompida
  }
  if (uint32_t(millis() - ultimoStatus) >= 30000) {
    ultimoStatus = millis();
    status();
    capacidades();
  }
  delay(1);
}
