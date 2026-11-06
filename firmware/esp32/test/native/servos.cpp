#include <cassert>
#include <iostream>
#include <Arduino.h>
uint64_t testeMicros = 1000000;
SerialTeste Serial;
int anexos = 0, desligados = 0, escritas = 0;
uint32_t ultimos[2] = {0, 0};
uint32_t ledcSetup(uint8_t, uint32_t freq, uint8_t bits) { assert(freq == 50 && bits == 16); return freq; }
void ledcWrite(uint8_t i, uint32_t duty) { assert(duty <= 65535); ++escritas; ultimos[i] = duty; }
void ledcAttachPin(uint8_t pin, uint8_t) { assert(pin == 25 || pin == 26); ++anexos; }
void ledcDetachPin(uint8_t) { ++desligados; }
#define VIGIA_SERVOS
#include "../../src/main.cpp"
void exigir(const char *texto) { assert(Serial.saida.find(texto) != std::string::npos); }
void evento(const char *id, int angulo = 70, const char *animal = "ave", int repeticoes = 1) {
  JsonDocument doc;
  doc["tipo"]="evento"; doc["v"]=1; doc["id"]=id; doc["ts"]=agora();
  doc["validade_ms"]=2000; doc["animal"]=animal; doc["confianca"]=.99; doc["resposta"]="teste";
  JsonArray acoes=doc["acoes"].to<JsonArray>();
  for (int i=1;i<=2;++i) {
    JsonObject a=acoes.add<JsonObject>();
    a["esp32"]="torre1"; a["acao"]="servo";
    a["params"]["servo"]=i; a["params"]["angulo"]=angulo; a["params"]["duracao_ms"]=600;
    if (repeticoes != 1) {
      a["params"]["repeticoes"] = repeticoes;
      a["params"]["angulo_alternado"] = 110;
      a["params"]["duracao_ms"] = 400;
    }
  }
  std::string linha;serializeJson(doc,linha);Serial.saida.clear();processar(linha.c_str());
}
int main() {
  setup();assert(anexos==0);exigir("\"atuadores_habilitados\":true");
  processar("{\"tipo\":\"hora\",\"v\":1,\"ts\":1000000}");
  evento("invalido",180);exigir("parametros_servo_invalidos");assert(anexos==0);
  evento("humano",70,"pessoa");exigir("presenca_humana");assert(anexos==0);
  evento("valido");exigir("\"status\":\"recebido\"");assert(movimentoAtivo);
  const int antes=anexos; assert(antes==2);
  evento("valido");exigir("\"repetido\":true");assert(anexos==antes);
  evento("ocupado");exigir("servos_ocupados");assert(anexos==antes);
  testeMicros+=600000;atualizarServos();assert(movimentoAtivo);
  testeMicros+=600000;Serial.saida.clear();atualizarServos();assert(!movimentoAtivo);
  exigir("\"status\":\"executado\"");exigir("\"simulado\":false");assert(desligados==antes);
  evento("valido");exigir("\"repetido\":true");assert(anexos==antes);
  evento("limite-repeticoes",70,"ave",6);exigir("parametros_servo_invalidos");assert(anexos==antes);
  evento("tres-ciclos",70,"ave",3);assert(movimentoAtivo);
  auto pulsoInicial = ultimos[0];
  for (int fase=1;fase<=5;++fase) {
    testeMicros+=400000;atualizarServos();assert(movimentoAtivo);
    assert((ultimos[0]==pulsoInicial)==(fase%2==0));
  }
  testeMicros+=400000;atualizarServos();assert(movimentoAtivo);
  testeMicros+=600000;Serial.saida.clear();atualizarServos();assert(!movimentoAtivo);
  exigir("\"status\":\"executado\"");assert(ultimos[0]==0 && ultimos[1]==0);
  std::cout<<"PASSOU: boot sem PWM, limites, pessoa, movimento, retorno, desligamento, busy e deduplicacao.\n";
}
