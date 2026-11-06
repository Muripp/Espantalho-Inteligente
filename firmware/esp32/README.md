# Receptor USB do ESP32-WROVER

**Perfil físico com dois SG90:** veja [SERVOS.md](SERVOS.md). O texto abaixo
descreve o perfil original de simulação `esp32-wrover`.

Recebe eventos **do Raspberry Pi** após a detecção. Não executa visão computacional
na placa. Compatível com `processador/canal_esp32/serial_uart.py`, JSON v1 por
linha, 115200 baud, identidade `torre1`.

Esta versão é exclusivamente de **simulação**: não configura GPIO, servo,
buzzer ou relé. Responde `ack recebido` e `ack executado`, ambos com
`dados.simulado: true`. `executado` confirma apenas a simulação, não uma ação
física. O processador atual mostra o ACK como executado; use uma configuração
de diagnóstico e consulte o campo `simulado` no log.

## Compilar

Na raiz do repositório, com PlatformIO instalado:

```bash
.venv/bin/pio run -d firmware/esp32
```

A configuração fixa plataforma Espressif32 6.10.0 e ArduinoJson 7.4.2,
framework Arduino e placa `esp-wrover-kit`. O perfil precisa ser confirmado
para a placa física antes de upload; não usa PSRAM nem pinos específicos.

Validação em 29/10/2026: compilação **SUCCESS**, PlatformIO 6.2.0,
Arduino-ESP32 2.0.17 e ArduinoJson 7.4.2. RAM estática 22840 bytes (7%),
programa 282205 bytes (21,5% da partição). Binário em
`.pio/build/esp32-wrover/firmware.bin`; SHA-256
`0f6e9e51da3e6633297c5de773876eae29d005f7e10c45d4a86ff2b6c2086f7b`.
Log completo: `testes/pi/firmware-build.log` na raiz do repositório.

A consulta via esptool identificou ESP32-D0WD-V3, revisão 3.0, cristal de
40 MHz e flash física de 16 MB (`testes/pi/esp32-chip.txt`). O perfil atual
usa apenas os primeiros 4 MB, sem PSRAM, suficiente para o receptor USB;
não é necessário reparticionar para aproveitar toda a flash neste teste.

Os downloads inicialmente falharam por conexão e a extração esgotou o tmpfs
de `/tmp`. As ferramentas foram movidas para `.pio-core/` na raiz, ignorada
pelo Git; o `core_dir` no PlatformIO usa essa pasta no cartão SD.
`pip check` e `git diff --check` passaram. Firmware gravado após autorização
explícita do usuário em 29/10/2026; resultados de bancada abaixo.

O teste nativo abaixo compila o código real do receptor com substitutos de
serial/relógio, usando a biblioteca ArduinoJson real. Passou nos casos de
sincronização, ACKs, duplicação, expiração, presença humana, destino incorreto,
linha longa e passagem pelo limite de `millis()`. Revelou e permitiu corrigir
o uso de `JsonObject` no lugar de `JsonObjectConst` ao validar `params`.
Esse teste não substitui a validação elétrica e serial na placa.

```bash
g++ -std=c++11 -Ifirmware/esp32/test/native \
  -Ifirmware/esp32/.pio/libdeps/esp32-wrover/ArduinoJson/src \
  firmware/esp32/test/native/protocolo.cpp -o testes/pi/teste-protocolo-nativo
testes/pi/teste-protocolo-nativo
```

Após gravar, com todos os atuadores desconectados, executar o teste serial:

```bash
.venv/bin/python -m ferramentas.testar_protocolo_esp32 --atuadores-desconectados
```

Ele aguarda identificar o firmware de simulação antes de transmitir eventos,
valida ACKs, repetição, validade e rejeição de `pessoa`, e salva um log em
`testes/pi/`. Executado contra a placa com sucesso após a gravação.

## Resultado na placa — 29/10/2026, 21:06

- Upload via CH340 a 115200 baud concluído com `SUCCESS`, hashes dos dados
  verificados (`testes/pi/esp32-upload.log`).
- Firmware identificado como `vigia-receptor-1.0.0`, nó `torre1`, modo
  `simulacao`, `atuadores_habilitados=false`.
- Teste serial real passou: sincronização de hora, ACK recebido/executado,
  duplicata identificada com `repetido=true`, rejeição de evento expirado e
  rejeição de `pessoa`. Todos os ACKs com `simulado=true`.
  Log: `testes/pi/esp32-protocolo-20261029-210636.jsonl`.
- Observação passiva durante 65 segundos: status com uptime 0, 30 e 60 s,
  sem novos resets após a inicialização. O loop repetitivo `RTCWDT_RTC_RESET`
  observado no firmware anterior não ocorreu nessa janela. Isso não substitui
  ensaio prolongado de estabilidade. Log: `testes/pi/esp32-estabilidade.log`.
- Atuadores permaneceram desconectados. Nenhuma ação física implementada.
- Pipeline webcam → detector → decisor com canal serial executado por 40 s:
  38 análises, todas `pessoa_perto`, média de inferência 878 ms. ESP32 reconhecido
  online com capacidades de simulação. Nenhum evento enviado, pois a presença
  humana bloqueou todas as decisões. O envio/ACK foi validado separadamente
  pelo teste serial acima. Log: `testes/pi/esp32-pipeline.log`.
- Encerramento por SIGINT tratado normalmente (`timeout` retorna 124).
  Câmera e serial liberadas; serviço `vigia` continuou inativo.

Configuração opcional para testar o pipeline real com este firmware:

```bash
.venv/bin/python -m processador --config processador/config_pi_esp32_teste.yaml
```

Essa configuração abre a serial e envia eventos reais do decisor para
simulação no ESP32. Usar somente com o firmware acima e atuadores desconectados.
As configurações originais e a configuração com canal vazio foram preservadas.

Fontes de API: [Serial do Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html)
e [ArduinoJson 7](https://arduinojson.org/v7/api/).

## Comportamento

- Ao ligar e a cada 30 segundos: `status` e `capacidades`, indicando simulação.
- `hora`: sincroniza o relógio com o Pi; obrigatório antes de aceitar eventos.
- `consulta`: devolve status e capacidades (extensão opcional de diagnóstico).
- `evento`: valida identidade do destino, ações, confiança, versão e validade;
  confirma ou devolve `ack erro`. Nunca toca nos atuadores.
- Rejeita evento classificado como `pessoa`; o bloqueio de animal junto de uma
  pessoa continua sendo responsabilidade do decisor no Pi.
- Mantém os últimos 20 IDs aceitos em RAM; repetição só devolve confirmação,
  sem processar novamente. Reiniciar a placa apaga esse histórico.
- Máximo de 1024 bytes por linha incluindo newline. Linhas inválidas, grandes
  ou interrompidas são descartadas; mensagens de debug começam com `#`.
- Validade permitida de 1 a 10000 ms; timestamp mais de 1000 ms no futuro
  é rejeitado. Usa relógio monotônico de 64 bits para evitar wrap do timestamp.

Exemplo de sequência transmitida pelo Pi (substituir `ts` pela hora Unix atual
em milissegundos; números antigos serão rejeitados):

```json
{"tipo":"hora","v":1,"ts":1793316000000}
{"tipo":"evento","v":1,"id":"ev-teste-1","ts":1793316000000,"animal":"ave","confianca":0.9,"resposta":"predador","validade_ms":2000,"acoes":[{"esp32":"torre1","acao":"som","params":{"faixa":3,"duracao_ms":1000}}]}
```

## Plano antes de gravar

Backup original concluído: `testes/pi/esp32-backup-original-16mb.bin`,
16777216 bytes, SHA-256
`f7691573097d4d81ad17a715f1b6ea697682339a4c371c2fa090b0b6c63a6de0`.
A leitura via esptool terminou com sucesso. A flash não foi alterada.
Consulta de eFuses somente leitura concluída: `FLASH_CRYPT_CNT=0`,
`ABS_DONE_0=False` e `ABS_DONE_1=False` (criptografia da flash e Secure Boot
desativados); resumo em `testes/pi/esp32-efuses.txt`. A consulta
`get_security_info` não é implementada neste chip; usou-se `espefuse summary`.
Foram instaladas as dependências da ferramenta, incluindo `bitstring==4.3.1`:
a versão 5 removeu `BitStream`, exigido pelo esptool 4.5.1.
`pip check` passou após o ajuste. Nenhum eFuse foi gravado.

Plano concreto de upload após autorização: usar esptool via CH340 em
`/dev/ttyUSB0`, 115200 baud, para gravar bootloader, tabela de partições,
dados de seleção de aplicação e receptor compilados pelo PlatformIO:

```bash
.venv/bin/pio run -d firmware/esp32 -t upload --upload-port /dev/ttyUSB0
```

Esse comando substitui o programa atual. Não executar sem autorização.
Não usar `erase_flash` nem comandos de gravação de eFuses. Manter atuadores
desconectados e executar o teste serial acima após upload. Validar pelo menos
60 segundos sem reinicializações antes de conectar o pipeline de visão.

1. Manter todos os atuadores desconectados e o serviço `vigia` inativo.
2. Confirmar modelo da placa/chip e tamanho da flash; salvar backup do conteúdo
   atual se a leitura for permitida pela proteção da placa.
3. Compilar e apresentar resultado e arquivos binários para revisão.
4. Obter autorização para substituir o firmware atual. Não apagar toda a flash
   indiscriminadamente nem alterar eFuses.
5. Gravar apenas após autorização; verificar estabilidade, mensagens de status,
   sincronização, ACKs, evento expirado e deduplicação, sem atuadores.
6. Só depois integrar webcam e canal serial em configuração separada de teste.

Não habilitar atuadores físicos nesta versão. As detecções incorretas observadas
no Pi continuam pendentes e não são corrigidas pelo firmware receptor.
