// Arduino-ESP32 2.x. Captura serial continua durante todas as fases de movimento.
constexpr uint8_t PINOS_SERVO[] = {25, 26};
bool movimentoAtivo = false;
String eventoAtivo;
uint32_t inicioMovimento = 0;
bool selecionados[2] = {false, false};
uint32_t duracoes[2] = {0, 0};
int angulos[2] = {90, 90};
int alternados[2] = {90, 90};
uint8_t fases[2] = {1, 1};
int ultimaFase[2] = {-1, -1};

void escreverServo(size_t i, int angulo) {
  const uint32_t pulso = 1000 + uint32_t(angulo) * 1000 / 180;
  ledcWrite(i, pulso * 65535UL / 20000);
}

bool validarServos(JsonArrayConst acoes) {
  if (acoes.size() > 2) return false;
  bool usados[2] = {false, false};
  for (JsonObjectConst a : acoes) {
    JsonObjectConst p = a["params"];
    if (!p["servo"].is<int>() || !p["angulo"].is<int>() || !p["duracao_ms"].is<int>()) return false;
    int i = p["servo"].as<int>() - 1;
    int angulo = p["angulo"];
    int duracao = p["duracao_ms"];
    if (i < 0 || i > 1 || usados[i] || angulo < 60 || angulo > 120 || duracao < 300 || duracao > 2000) return false;
    if (!p["repeticoes"].isNull() && !p["repeticoes"].is<int>()) return false;
    int repeticoes = p["repeticoes"] | 1;
    if (repeticoes < 1 || repeticoes > 5) return false;
    bool alterna = !p["angulo_alternado"].isNull();
    if (alterna && (!p["angulo_alternado"].is<int>() || p["angulo_alternado"].as<int>() < 60 || p["angulo_alternado"].as<int>() > 120)) return false;
    if (repeticoes > 1 && !alterna) return false;
    if (duracao * (alterna ? 2 * repeticoes : 1) + 600 > 8000) return false;
    usados[i] = true;
  }
  return true;
}

void iniciarServos(const char *id, JsonArrayConst acoes) {
  eventoAtivo = id;
  movimentoAtivo = true;
  inicioMovimento = millis();
  for (JsonObjectConst a : acoes) {
    JsonObjectConst p = a["params"];
    size_t i = p["servo"].as<int>() - 1;
    selecionados[i] = true;
    duracoes[i] = p["duracao_ms"].as<uint32_t>();
    angulos[i] = p["angulo"];
    alternados[i] = p["angulo_alternado"] | 90;
    fases[i] = p["angulo_alternado"].isNull() ? 1 : 2 * (p["repeticoes"] | 1);
    ultimaFase[i] = 0;
    ledcSetup(i, 50, 16);
    escreverServo(i, angulos[i]);
    ledcAttachPin(PINOS_SERVO[i], i);
  }
}

void atualizarServos() {
  if (!movimentoAtivo) return;
  uint32_t decorrido = uint32_t(millis() - inicioMovimento);
  bool algum = false;
  for (size_t i = 0; i < 2; ++i) {
    if (!selecionados[i]) continue;
    uint32_t tempoMovimento = duracoes[i] * fases[i];
    int fase = decorrido >= tempoMovimento ? fases[i] : decorrido / duracoes[i];
    if (fase != ultimaFase[i]) {
      escreverServo(i, fase == fases[i] ? 90 : (fase % 2 ? alternados[i] : angulos[i]));
      ultimaFase[i] = fase;
    }
    if (decorrido >= tempoMovimento + 600) {
      ledcWrite(i, 0);
      ledcDetachPin(PINOS_SERVO[i]);
      selecionados[i] = false;
    } else algum = true;
  }
  if (!algum) {
    movimentoAtivo = false;
    vistos[proximoVisto] = eventoAtivo;
    proximoVisto = (proximoVisto + 1) % 20;
    ack(eventoAtivo.c_str(), "executado");
  }
}
