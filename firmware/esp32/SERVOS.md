# Teste de dois SG90 no WROVER-DEV

Perfil físico novo: `esp32-servos`, firmware `vigia-servos-1.2.0`.
O perfil original `esp32-wrover` continua sendo apenas simulação.

- Sinal servo 1: GPIO25; sinal servo 2: GPIO26.
- Alimentação externa regulada de 5 V; GND comum com o ESP.
- Nenhum PWM é habilitado no boot.
- Uma ação `servo` exige `params: {servo: 1 ou 2, angulo: 60..120, duracao_ms: 300..2000}`.
- Com `angulo_alternado` e `repeticoes` (1..5), alterna os dois ângulos,
  mantendo cada posição por `duracao_ms`. A série completa é limitada a 8 s.
- Ao terminar, retorna a 90 graus por 600 ms e desliga o PWM.
- Até dois servos por evento; todos os parâmetros são validados antes do movimento.
- Durante o movimento, outro evento recebe `erro: servos_ocupados`.
- Duplicatas em andamento recebem `recebido`; concluídas recebem `executado`, sem repetir movimento.
- O ACK `executado` tem `simulado: false`: confirma o término dos sinais enviados, sem medir posição física.
- Mantém validação de destino, relógio, expiração e rejeição de `pessoa`.

Compilar e gravar o perfil físico:

```bash
.venv/bin/pio run -d firmware/esp32 -e esp32-servos
.venv/bin/pio run -d firmware/esp32 -e esp32-servos -t upload --upload-port /dev/ttyUSB0
```

Teste de bancada, sem processador usando a serial:

```bash
.venv/bin/python -m ferramentas.testar_servos
# Ou apenas um:
.venv/bin/python -m ferramentas.testar_servos --servo 1
```

O script verifica firmware e pinos antes de transmitir movimento.
Servo 1: 70 graus; servo 2: 110 graus; ambos retornam ao centro.
Confira visualmente o movimento. Logs em `testes/pi/servos-*.jsonl`.

Após validar na bancada, encerrar o processador anterior antes de iniciar a integração:

```bash
.venv/bin/python -m processador --config processador/config_servos.yaml
```

Essa configuração, também aplicada em `processador/config.yaml`, usa webcam, dashboard, threshold do dashboard e ações de servo
em lugar das receitas de som/luz. Cada reconhecimento acima do threshold gera
três idas e voltas (70–110 graus, 400 ms por posição), simultâneas nos dois servos.
A configuração não usa cooldown: o processador aguarda o ACK final antes da próxima
análise, evitando sobreposição. Presença humana reconhecida bloqueia a ação. O modelo pode produzir
falsos positivos. Pausar o feed do dashboard pausa somente a visualização.

## Bancada em 05/11/2026

- Compilação e upload do perfil `esp32-servos`: SUCCESS, hashes verificados.
- RAM estática: 22976 bytes; programa: 289969 bytes.
- Testes nativos de protocolo em simulação e de controle de servos: passaram.
- Teste serial físico: ambos os eventos confirmados com `recebido` e `executado`,
  `simulado: false`. Log: `testes/pi/servos-20261105-202742.jsonl`.
- Movimento mecânico ainda depende da confirmação visual do operador.
- Na primeira rodada, o dashboard permaneceu com ESP32 virtual durante a bancada.

## Integração com reconhecimento — 05/11/2026

- Firmware `vigia-servos-1.2.0` compilado e gravado com hashes verificados.
- Três ciclos por comando validados no teste nativo, além de limites e deduplicação.
- Sete testes Python passaram: threshold, geração da receita e bloqueio por pessoa.
- Placa confirmou séries de três movimentos nos dois servos; log:
  `testes/pi/servos-20261105-203444.jsonl`.
- Processador iniciado com `processador/config_servos.yaml`: webcam e ESP real online,
  firmware e pinos confirmados pela serial; dashboard online.
- Nas primeiras imagens dessa integração, nenhum animal foi detectado.
  O teste de bancada valida os comandos; aguarda-se um animal na câmera para
  observar o acionamento automático nessa sessão.

## Controles e indicação no dashboard

O painel da câmera exibe o animal e a confiança durante a reação. O estado muda
com os ACKs do ESP: comando enviado → movimento recebido → concluído, ou erro.
Uma faixa sobre o vídeo destaca o acionamento enquanto está em andamento.

Os botões **Testar servo 1**, **Testar servo 2** e **Testar os dois** executam a
receita de três ciclos. Funcionam com o feed pausado e usam o próprio processador,
que mantém a única conexão serial. Não geram detecções de animais: aparecem no
histórico como `Teste manual`. Durante um movimento, os botões ficam bloqueados.

- `GET /api/servos`: estado da conexão, movimento e disponibilidade.
- `POST /api/servos/testar`, JSON `{"servo":"1"}`, `"2"` ou `"ambos"`:
  solicita um teste; retorna 409 se ocupado, 503 se desconectado.
- Pedidos não consumidos expiram em 10 s; heartbeat perdido desabilita os controles.
- Validação: 13 testes Python passaram; os três alvos foram testados contra o
  ESP real via API, com ACKs recebido/executado. Testes de UI no Chromium com
  respostas simuladas validaram cliques, indicação, confiança e estados offline.
