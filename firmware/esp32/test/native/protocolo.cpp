#include <cassert>
#include <iostream>
#include <Arduino.h>
uint64_t testeMicros = 1000000;
SerialTeste Serial;
#include "../../src/main.cpp"

void exigir(const char *texto) {
  if (Serial.saida.find(texto) == std::string::npos) {
    std::cerr << "Faltou: " << texto << "\nSaida: " << Serial.saida;
    std::abort();
  }
}

void evento(const char *id, int64_t ts, const char *animal = "ave", const char *destino = "torre1") {
  JsonDocument doc;
  doc["tipo"] = "evento"; doc["v"] = 1; doc["id"] = id;
  doc["ts"] = ts; doc["validade_ms"] = 2000;
  doc["animal"] = animal; doc["confianca"] = .9; doc["resposta"] = "predador";
  JsonObject a = doc["acoes"].to<JsonArray>().add<JsonObject>();
  a["esp32"] = destino; a["acao"] = "som";
  a["params"]["duracao_ms"] = 100;
  std::string linha; serializeJson(doc, linha);
  Serial.saida.clear(); processar(linha.c_str());
}

int main() {
  setup(); exigir("\"atuadores_habilitados\":false");
  evento("antes-hora", 1000000); exigir("relogio_nao_sincronizado");
  processar("{\"tipo\":\"hora\",\"v\":1,\"ts\":1000000}");
  assert(sincronizado);
  evento("valido", agora()); exigir("\"status\":\"recebido\"");
  exigir("\"status\":\"executado\""); exigir("\"simulado\":true");
  assert(recebidos == 1);
  evento("valido", agora()); exigir("\"repetido\":true"); assert(recebidos == 1);
  evento("velho", agora() - 5000); exigir("expirado_ou_futuro");
  evento("futuro", agora() + 2000); exigir("expirado_ou_futuro");
  evento("humano", agora(), "pessoa"); exigir("presenca_humana");
  evento("destino", agora(), "ave", "outra-torre"); exigir("acao_ou_destino_invalido");
  assert(recebidos == 1);
  // Parsing real pelo loop: linha grande, seguida de consulta válida.
  Serial.saida.clear(); Serial.entrada = std::string(1100, 'x') + "\n{\"tipo\":\"consulta\",\"v\":1}\n";
  while (Serial.available()) loop();
  exigir("descartando"); exigir("\"tipo\":\"capacidades\"");
  // Timestamp continua correto ao atravessar o wrap de millis().
  const auto antes = agora(); testeMicros += uint64_t(1) << 42;
  assert(agora() > antes); evento("apos-wrap", agora());
  exigir("\"status\":\"executado\""); assert(recebidos == 2);
  std::cout << "PASSOU: sincronizacao, ACKs, repeticao, expiracao, pessoa, destino, limite de linha e relogio.\n";
}
