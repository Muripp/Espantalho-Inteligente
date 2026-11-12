# VIGIA: espantalho inteligente

Link da apresentação: https://www.canva.com/design/DAHau4RbQMw/Udgdpd-J2kZLnamWnOs6jg/edit

Uma câmera fica olhando a plantação. Quando aparece um bicho, um modelo de visão computacional diz **qual bicho é**. O sistema escolhe **o susto certo** pra ele (som de gavião pra ave, sirene pra porco...) e manda um **ESP32** executar. Tudo fica registrado e aparece num **dashboard**.

```
  📷 câmera ──► 🧠 Raspberry Pi ──────────► 🤖 ESP32 ──► 🔊 som · 💡 luz · 💧 jato d'água
                 │  modelo YOLO   evento       (executa)
                 │  regras        ◄── ack ───
                 │
                 ├──► 💾 memória própria (sempre)
                 └──► 📊 dashboard (opcional)
```

> **Documentação completa** (arquitetura, decisões, diagramas): vault do Obsidian em `Documents\VIGIA`. Comece por `00 - Início` e pelo Canvas `Fluxo geral`.

---

## Sumário
1. [Início rápido](#1-início-rápido)
2. [Como funciona](#2-como-funciona)
3. [Estrutura do projeto](#3-estrutura-do-projeto)
4. [O processador (Raspberry Pi)](#4-o-processador-raspberry-pi)
5. [Respostas por animal (`respostas.yaml`)](#5-respostas-por-animal-respostasyaml)
6. [Comunicação com o ESP32](#6-comunicação-com-o-esp32)
7. [Memória local do Pi](#7-memória-local-do-pi)
8. [Webapp e dashboard](#8-webapp-e-dashboard)
9. [Instalar no Raspberry Pi](#9-instalar-no-raspberry-pi)
10. [Testar sem hardware](#10-testar-sem-hardware)
11. [O modelo](#11-o-modelo)
12. [Referência de configuração](#12-referência-de-configuração)
13. [Problemas comuns](#13-problemas-comuns)
14. [Status e próximos passos](#14-status-e-próximos-passos)

---

## 1. Início rápido

### No PC (Windows): ver o dashboard e testar o modelo
1. Dê **duplo clique em `iniciar.bat`**. Ele:
   - usa o Python do treino (`D:\espantalho_treino\venv`) se existir, senão o `python` do sistema;
   - instala o que faltar (`requirements.txt`);
   - abre 2 janelas (webapp e processador) e o navegador em **http://localhost:8000**.
2. No dashboard, clique em **📁 Selecionar pasta** e escolha uma pasta com fotos.
3. Cada foto passa pelo modelo e aparece numa tabela: animal, confiança, decisão, resposta, data e tempo.

Pra desligar, feche as 2 janelas pretas.

Na mão (de dentro desta pasta):
```bash
python -m uvicorn webapp.servidor:app --port 8000     # janela 1: webapp
python -m processador                                 # janela 2: processador
```

### No Raspberry Pi: rodar no campo
```bash
cd ~/vigia
bash raspberry/instalar.sh          # ESP32 no cabo USB   (use --mqtt se for pelo Wi-Fi)
journalctl -u vigia -f              # ver o que está acontecendo
```
Detalhes na [seção 9](#9-instalar-no-raspberry-pi).

---

## 2. Como funciona

**O Raspberry Pi pensa, o ESP32 executa, o webapp mostra.**

### O fluxo (combinado com o grupo)
```
 fica vendo a câmera
        │  (tira foto quando algo se mexe, de 10 em 10 s, ou quando o PIR do ESP32 avisa)
        ▼
 processa a imagem no modelo  ──►  "ave 91%, em (120,40)-(380,300)"
        │
        ▼
 viu animal? ── não ──► nada é registrado
        │ sim
        ▼
 decide  ──►  tem pessoa perto?          → não age (segurança)
              espantou esse bicho há pouco? → espera (cooldown)
              senão: sorteia uma resposta do respostas.yaml
        │
        ▼
 EVENTO ──┬──► ESP32:   "ave → predador: som faixa 3 + estrobo"   (só quando vai agir)
          ├──► memória: memoria/eventos.jsonl + foto              (sempre que viu animal)
          └──► dashboard (opcional)
```

| Situação | Vai pro ESP32? | Vai pra memória? |
|---|---|---|
| Animal, sem pessoa, fora do cooldown → **`espantou`** | ✅ | ✅ |
| Animal + pessoa perto → **`pessoa_perto`** | ❌ | ✅ |
| Mesmo animal espantado há pouco → **`aguardando`** | ❌ | ✅ (no máximo 1 a cada 10 s por animal) |
| Nenhum animal → **`nada`** | ❌ | ❌ |

### As 3 partes
| Parte | Pasta | O que faz |
|---|---|---|
| **Processador** | `processador/` | Roda no Raspberry Pi (ou no PC pra testar): câmera → modelo → decisão → ESP32 + memória |
| **Comunicação com o ESP32** | `processador/canal_esp32/` | Manda o evento pelo cabo (serial) ou pelo Wi-Fi (MQTT), confere a resposta e reenvia se precisar |
| **Webapp** | `webapp/` | Servidor + dashboard que mostra cada animal visto, com o teste de pasta |

### "Plugins": por que dá pra trocar peças sem mexer no resto
A câmera e o ESP32 ficam atrás de **interfaces**: o resto do código não sabe o que tem do outro lado.

| Interface | Métodos | Opções (`config.yaml`) |
|---|---|---|
| `FonteDeImagens` (`fontes/base.py`) | `proxima()`, `pedir_foto()` | `picamera` · `webcam` · `pasta` · `webapp` |
| `CanalESP32` (`canal_esp32/base.py`) | `enviar(evento)`, `receber()` | `serial` · `mqtt` · `webapp` (ESP32 virtual) · `vazio` |

Trocar de webcam pra Picamera, ou de cabo pra Wi-Fi, é **mudar uma linha da configuração**.

---

## 3. Estrutura do projeto

```
vigia/
├── iniciar.bat                  abre webapp + processador + navegador (Windows)
├── requirements.txt             dependências no PC
│
├── compartilhado/
│   └── mensagens.py             formato de TODAS as mensagens (dataclasses): ImagemInfo, Deteccao,
│                                ResultadoAnalise, EventoESP32, MensagemESP32
│
├── processador/                 ─── roda no Raspberry Pi ───
│   ├── __main__.py              o loop principal  (python -m processador)
│   ├── config.yaml              configuração no PC (webapp + ESP32 virtual)
│   ├── config_pi.yaml           configuração no Pi (picamera + serial)
│   ├── respostas.yaml           animal → resposta → ações  (o "banco de respostas")
│   ├── detector.py              roda o modelo ONNX e devolve as detecções
│   ├── decisor.py               regras: confiança, pessoa, cooldown, sorteio → EventoESP32
│   ├── memoria.py               grava memoria/eventos.jsonl, fotos/ e esp32.jsonl
│   ├── publicador.py            manda pro dashboard (com fila se cair) e desenha as caixas
│   ├── modelos/espantalho_aves.onnx    o modelo (9 classes, 10,6 MB)
│   ├── fontes/                  de onde vêm as fotos
│   │   ├── base.py              interface
│   │   ├── movimento.py         QUANDO tirar foto (movimento / periódico / PIR)
│   │   ├── picamera.py          câmera do Raspberry Pi
│   │   ├── webcam.py            câmera USB / notebook
│   │   ├── pasta.py             lê fotos de uma pasta (finge ser a câmera)
│   │   └── webapp.py            fotos do botão "Testar pasta" do dashboard
│   └── canal_esp32/             como falar com o ESP32
│       ├── base.py              interface
│       ├── transporte.py        protocolo + ack + reenvio (base do serial e do MQTT)
│       ├── serial_uart.py       ESP32 no cabo USB / UART
│       ├── mqtt.py              ESP32 pelo Wi-Fi (broker Mosquitto)
│       ├── webapp.py            "ESP32 virtual" dentro do dashboard
│       └── vazio.py             só mostra no terminal
│
├── webapp/                      ─── dashboard ───
│   ├── servidor.py              FastAPI: API + páginas
│   ├── banco.py                 SQLite (webapp/dados/vigia.db, criado sozinho)
│   └── static/                  index.html, app.js, style.css
│
├── raspberry/                   ─── instalação no Pi ───
│   ├── instalar.sh              instala tudo e cria o serviço
│   ├── vigia.service            serviço systemd (liga no boot, reinicia se cair)
│   └── requirements-pi.txt
│
└── ferramentas/
    └── esp32_falso.py           ESP32 de mentira (serial ou MQTT): testes + referência pro firmware
```

---

## 4. O processador (Raspberry Pi)

### O loop (`processador/__main__.py`)
```
repete pra sempre:
  1. msg = canal.receber()        ← o que o ESP32 disse (não trava)
       "sensor" (PIR)  → pede uma foto pra câmera agora
       "ack"           → grava em memoria/esp32.jsonl e avisa o dashboard
       (por baixo, o canal reenvia eventos sem resposta e percebe ESP32 sumido)
  2. img = fonte.proxima()        ← tem foto nova? (não trava; se não, espera 50 ms)
  3. deteccoes = detector.detectar(img)
  4. decisao = decisor.decidir(deteccoes)
  5. se vai agir:      canal.enviar(evento)          → ESP32
  6. se viu animal:    memoria.guardar(...)          → memória do Pi
                       publicador.publicar(...)      → dashboard (se webapp.ativado)
```

Regras:
- **Nada trava o loop.** Se o ESP32 ou o dashboard cair, o processador continua.
- **Uma foto por vez**, sempre a mais recente.
- Tudo aparece no terminal (ou no `journalctl` do Pi), com o `id` de cada evento.

### O decisor, na ordem
1. Joga fora detecções abaixo do corte de confiança **daquele animal** (ave 0.35, resto 0.45).
2. Tem pessoa? → `pessoa_perto` (não age).
3. Sobrou algum animal? Se não → `nada`.
4. Pega o animal mais confiante.
5. Já espantou esse animal há menos de `cooldown_s`? → `aguardando`.
6. Sorteia uma resposta da regra do animal (ou da regra `padrao`).
7. Monta **um `EventoESP32`** com o animal, a resposta e as ações → `espantou`.

No "Testar pasta" o cooldown é ignorado, porque cada foto é independente.

### Quando a câmera tira foto (`fontes/movimento.py`)
| Gatilho | Quando |
|---|---|
| `movimento` | Mais de 0,4% da imagem mexeu (compara com o "fundo" aprendido) |
| `periodico` | 10 s sem foto (pega ave pousada e parada) |
| `pir` | O sensor PIR do ESP32 avisou |

No máximo 2 fotos por segundo.

---

## 5. Respostas por animal (`respostas.yaml`)

Três camadas, e é isso que deixa escalar:

```
  REGRA (por animal)          RESPOSTA (receita com nome)        AÇÃO (o que o ESP32 faz)
  ave ─────────────────────►  "predador" ─────────────────────►  som faixa 3   (torre1)
   confiança ≥ 0.35                                          └►  led estrobo   (torre1)
   cooldown 30 s              "sirene"   ─────────────────────►  som faixa 7   (torre1)
   sorteio predador 3 : 1 sirene
```

```yaml
respostas:                          # receitas reutilizáveis
  predador:
    - { esp32: torre1, acao: som, params: { faixa: 3, volume: 85, duracao_ms: 4000 } }
    - { esp32: torre1, acao: led, params: { padrao: estrobo, duracao_ms: 4000 } }
  sirene:
    - { esp32: torre1, acao: som, params: { faixa: 7, volume: 100, duracao_ms: 5000 } }

regras:                             # qual animal usa qual receita
  ave:    { confianca_min: 0.35, cooldown_s: 30, respostas: { predador: 3, sirene: 1 } }
  porco:  { confianca_min: 0.45, cooldown_s: 20, respostas: { sirene: 1, latido: 1 } }
  padrao: { cooldown_s: 30, respostas: { sirene: 1 } }      # qualquer animal sem regra própria
  pessoa: { bloqueia_tudo: true }                           # tem gente → ninguém age

padroes:
  confianca_min: 0.45
  validade_ms: 2000                 # evento mais velho que isso não adianta mais
```

- Os números em `respostas` são **pesos do sorteio**: `predador: 3, sirene: 1` = 3 de cada 4 vezes usa "predador". Variar o susto evita que o bicho se acostume.
- ⚠️ **Use `esp32:`, nunca `no:`.** No YAML, `no` é lido como "falso".
- O arquivo é conferido ao ligar. Se uma regra usar uma resposta que não existe, o processador avisa e não inicia.

| Quero... | Faço |
|---|---|
| Bicho novo | Treino o modelo com a classe nova + acrescento uma linha em `regras` |
| Susto novo com o hardware que já existe | Crio uma receita em `respostas` e uso numa regra |
| Hardware novo (ex.: servo) | Ensino a ação `servo` ao firmware → já dá pra usar em qualquer receita |
| Mais um ESP32 | Dou um nome (`bomba1`), uso `esp32: bomba1` nos passos e adiciono a porta dele no config |

Depois de mudar, reinicie o processador (no Pi: `sudo systemctl restart vigia`).

---

## 6. Comunicação com o ESP32

> Explicação completa, com diagramas e checklist do firmware: vault → **`04 ESP32/Protocolo ESP32 ↔ Pi`**.

### Duas formas de ligar, mesmas mensagens
| | **Serial (cabo USB)** · ✅ escolhido | **MQTT (Wi-Fi)** |
|---|---|---|
| Quando usar | ESP32 perto do Pi | ESP32 longe, ou vários ESP32 |
| Config | `canal_esp32: { tipo: serial, portas: { torre1: /dev/ttyUSB0 } }` | `canal_esp32: { tipo: mqtt, broker: localhost }` |
| Uma mensagem é | **uma linha de JSON** + `\n`, 115200 baud | um publish com o JSON |
| Saber se o ESP32 caiu | 90 s sem nenhuma mensagem | na hora (testamento/LWT) |

Tópicos MQTT: `vigia/{esp32}/evento` (Pi → ESP32), `vigia/{esp32}/ack`, `/sensor`, `/status`, `/capacidades` (ESP32 → Pi) e `vigia/hora`.

### As mensagens
**Pi → ESP32**: o evento. Cada ESP32 recebe só as ações dele:
```json
{"tipo":"evento","v":1,"id":"ev-0e3837f7","ts":1793298781886,"animal":"ave","confianca":0.91,
 "resposta":"predador","acoes":[{"esp32":"torre1","acao":"som","params":{"faixa":3,"volume":85,"duracao_ms":4000}}],
 "validade_ms":2000}
```
E também `{"tipo":"hora","ts":...}`, que acerta o relógio do ESP32.

**ESP32 → Pi**:
| `tipo` | Quando | `dados` |
|---|---|---|
| `ack` | Ao receber **e** ao terminar um evento | `{"evento":"ev-...","status":"recebido"}` → `"executado"` (ou `"erro"`) |
| `status` | Ao ligar e a cada 30 s | `{"firmware":"1.0","uptime_s":3600,"rssi":-61}` |
| `capacidades` | Ao ligar | `{"acoes":["som","led","rele:1","parar"]}` |
| `sensor` | O PIR disparou | `{"sensor":"pir1","valor":1}` → o Pi tira foto na hora |

```json
{"tipo":"ack","v":1,"no":"torre1","dados":{"evento":"ev-0e3837f7","status":"executado"}}
```

### Entrega confiável
```
 Pi ── evento ev-0e38 ─────────────────►  ESP32
 Pi ◄──────────────── ack "recebido" ───  ESP32   (o Pi para de reenviar)
                                           ESP32 toca o som, pisca o led
 Pi ◄──────────────── ack "executado" ──  ESP32
```
- Sem ack em **1 s** → o Pi **reenvia**, no máximo 2 vezes, dentro dos 2 s de validade.
- O ESP32 guarda os últimos 20 ids: evento **repetido** só é confirmado de novo, **nunca executado 2×**.
- Se o Pi desiste, registra **`sem_resposta`** (memória + dashboard). O próximo animal gera outro evento normalmente.
- Serial: se o cabo sair, o Pi tenta reabrir a porta a cada 3 s, sozinho.

### O que o firmware precisa fazer (resumo)
1. Ler linha a linha; ignorar linhas que não começam com `{`.
2. `evento`: id repetido? Só confirma. Expirou? Manda `erro`. Senão: `ack recebido` → executa as ações em ordem → `ack executado`.
3. Ao ligar: `capacidades` + `status`. A cada 30 s: `status`.
4. Relé/bomba com **tempo máximo no firmware** (ex.: 10 s).
5. Prints de debug **nunca começam com `{`**.
6. Executar sem `delay()` longo (usar `millis()`), senão o ack atrasa e o Pi reenvia.

**`ferramentas/esp32_falso.py` faz exatamente isso em Python**: serve de referência pra escrever o firmware.

---

## 7. Memória local do Pi

A "caixa-preta" do espantalho: funciona **sem rede, sem ESP32 e sem dashboard**.

```
processador/memoria/
├── eventos.jsonl     uma linha JSON por animal visto (nunca é apagado)
├── esp32.jsonl       o que o ESP32 respondeu: acks, status, sem_resposta
└── fotos/            foto anotada de cada evento (nome começa pela data)
```

- Uma linha por evento: se o Pi desligar no meio, perde no máximo a última.
- Até `max_fotos` fotos (padrão 5000, uns 300 MB). Acima disso, apaga as **fotos** mais velhas. O `.jsonl` fica inteiro.
- **Levar pro dashboard:** copie a pasta `memoria` pro PC e use **📥 Importar memória do Pi**. Importar 2 vezes não duplica.

---

## 8. Webapp e dashboard

**http://localhost:8000**. FastAPI + SQLite + HTML/JS puro (Chart.js). Atualiza sozinho a cada 2 s.

### O que tem
| Parte | Mostra |
|---|---|
| Topo | 🟢/🔴 processador online · período (1 h / 24 h / 7 d / tudo) · 📥 Importar memória do Pi · Limpar dados |
| Cartões | Análises, sustos disparados, e quantas vezes cada animal (e pessoa) foi visto |
| **🧪 Testar pasta** | Escolhe uma pasta, cada foto vai pro modelo, e aparece uma tabela com miniatura, arquivo, animal + confiança, decisão, resposta e ações, outras detecções, data do arquivo, hora e tempo. Tem filtro por animal, **CSV**, testes anteriores e botão de parar |
| 🕒 Últimas análises | Feed ao vivo com foto |
| 📈 Animais por hora | Barras empilhadas |
| 📡 Eventos pro ESP32 | Animal → resposta → ações, com status (enviado / recebido / ✓ executado / sem_resposta) |
| Detalhe | Clicar em qualquer foto abre a imagem com as caixas e todos os dados |

### API (resumo)
| Rota | Pra quê |
|---|---|
| `POST /api/analises` | O processador publica um resultado |
| `GET /api/analises?lote=&animal=&limite=` · `/api/resumo?horas=` · `/api/eventos-esp32` · `/api/status` | Dados do dashboard |
| `POST /api/lotes` · `POST /api/simulador/imagem` · `GET /api/lotes/{id}` · `/csv` · `/cancelar` | Testar pasta |
| `GET /api/simulador/proxima-imagem` | O processador pega a próxima foto do teste |
| `POST /api/esp32-virtual/eventos` · `GET /api/esp32-virtual/mensagens` | ESP32 virtual (responde ack sozinho) |
| `POST /api/eventos-esp32/{id}/status` | Atualiza o status de um evento |
| `POST /api/limpar` | Apaga tudo |

Banco (`webapp/dados/vigia.db`): `analises`, `deteccoes`, `eventos_esp32`, `lotes`.

---

## 9. Instalar no Raspberry Pi

**Precisa de:** Raspberry Pi 4 ou 5 com Raspberry Pi OS Bookworm 64 bits, câmera oficial no conector CSI, e o ESP32 no USB (ou na mesma rede Wi-Fi). Internet só pra instalar.

1. Copie a pasta `vigia/` pro Pi (pendrive, `scp` ou `git clone`).
2. Rode:
   ```bash
   cd ~/vigia
   bash raspberry/instalar.sh          # ESP32 no cabo
   bash raspberry/instalar.sh --mqtt   # ESP32 pelo Wi-Fi (instala o Mosquitto)
   ```
   O script instala a câmera, o OpenCV e o numpy pelo `apt` e cria o `.venv` (com `--system-site-packages`, porque o `picamera2` só existe pelo apt). Depois instala o resto, dá permissão pra serial, **mede quanto tempo o modelo leva nesse Pi**, testa a câmera e cria o serviço `vigia`.
3. `sudo reboot` uma vez, pra valer a permissão da serial.
4. Ajuste `processador/config_pi.yaml`. A porta do ESP32 você descobre com `ls /dev/ttyUSB* /dev/ttyACM*`.

| Pra... | Comando |
|---|---|
| Ver se está rodando | `sudo systemctl status vigia` |
| Ver o log ao vivo | `journalctl -u vigia -f` |
| Reiniciar (depois de mudar config/respostas) | `sudo systemctl restart vigia` |
| Parar | `sudo systemctl stop vigia` |
| Rodar na mão | `sudo systemctl stop vigia && .venv/bin/python -m processador --config processador/config_pi.yaml` |

Exemplo de log:
```
canal.serial   porta /dev/ttyUSB0 aberta (torre1)
canal          -> torre1 evento ev-d312ecb2: cachorro -> sirene (1 ações)
processador    dog.jpg   espantou   cachorro sirene   230 ms | cachorro 92%
canal          <- torre1 ack ev-d312ecb2: recebido
canal          <- torre1 ack ev-d312ecb2: executado
```

---

## 10. Testar sem hardware

### Sem câmera: fotos de uma pasta
No dashboard, use **📁 Selecionar pasta**. Ou, pra simular o campo de verdade (cooldown e memória valendo), use no `config.yaml`:
```yaml
fonte:       { tipo: pasta, pasta: C:/fotos/campo, modo: camera }
canal_esp32: { tipo: vazio }          # mostra no terminal o que mandaria pro ESP32
webapp:      { ativado: false }       # só ESP32 + memória, como no campo sem rede
```

### Sem ESP32: o ESP32 falso
```bash
python ferramentas/esp32_falso.py --pty                 # Linux/Pi: cria uma porta virtual e mostra o caminho
python ferramentas/esp32_falso.py --serial COM5         # uma porta serial (ex.: par virtual do com0com no Windows)
python ferramentas/esp32_falso.py --mqtt localhost      # pelo broker MQTT
```
| Opção | Simula |
|---|---|
| `--perder 1` | O primeiro evento se perde → o Pi tem que reenviar |
| `--perder-ack 1` | A resposta se perde → o ESP32 recebe o evento 2× e não pode executar de novo |
| `--pir 20` | O sensor PIR dispara a cada 20 s |
| `--rapido` | Não espera a duração das ações |
| `--nome bomba1` | Outro ESP32 |

### ESP32 de verdade ligado no PC
```yaml
canal_esp32: { tipo: serial, portas: { torre1: COM5 } }     # porta no Gerenciador de Dispositivos
```

### Cenários já testados (29/10, com câmera e ESP32 simulados)
- ✅ Teste de pasta: 32/32 fotos, ~80 ms por foto
- ✅ Serial: evento perdido → reenviou e executou
- ✅ Serial: resposta perdida → recebeu 2× e **não** executou de novo
- ✅ ESP32 desligado → 2 tentativas → `sem_resposta`
- ✅ MQTT com 2 ESP32: cada um recebeu só as suas ações
- ✅ PIR → o Pi recebeu o sensor
- ✅ ESP32 caiu sem avisar → o testamento chegou na hora
- ✅ Picamera simulada: foto por movimento → evento → memória
- ✅ Memória do "modo campo" importada no dashboard

---

## 11. O modelo

`processador/modelos/espantalho_aves.onnx`: YOLO11 nano, 640×640, 10,6 MB. Roda só com `onnxruntime` (sem PyTorch e sem GPU).

**Classes:** `ave` · `cachorro` · `porco` · `cavalo` · `rato` · `vaca` · `gato` · `pessoa` · `outro_animal` (qualquer outro bicho: ovelha, cabra, raposa, cobra...).

| Teste com 240 fotos que o modelo nunca viu | Acertos |
|---|---|
| ave (corte 0.35) | 37/40 |
| gato | 35/40 |
| cachorro | 34/40 |
| vaca | 32/40 |
| cavalo | 31/40 |
| outro_animal | 30/40 |
| **total** | **83%** (só 3 de 240 confundidos com porco) |

Porco e rato não entraram nesse teste, porque todas as fotos deles do Open Images foram usadas no treino.

O treino foi feito no projeto `projetos\espantalho` (`treinar_local.py` e `treinar_aves.py`). Velocidade: ~80 ms por foto no PC. No Raspberry Pi 4 deve ficar entre 300 e 600 ms (o `instalar.sh` mede). **O que mais vai melhorar o modelo: fotos tiradas pela própria câmera do espantalho, no lugar de verdade.**

---

## 12. Referência de configuração

`processador/config.yaml` (PC) ou `processador/config_pi.yaml` (Pi). Caminhos relativos partem da pasta `processador/`.

```yaml
dispositivo: pi-campo-1              # nome que aparece no dashboard
modelo: modelos/espantalho_aves.onnx
respostas: respostas.yaml
log: INFO                            # DEBUG mostra tudo (inclusive cada status do ESP32)
```

### `fonte`
| `tipo` | Opções |
|---|---|
| `picamera` | `largura` (1280), `altura` (720), `rotacao` (0 \| 180), `quadros_s` (10) + opções de movimento |
| `webcam` | `camera` (0), `largura`, `altura` + opções de movimento |
| `pasta` | `pasta` (caminho), `modo` (`camera` = finge ser a câmera · `teste` = sem cooldown) |
| `webapp` | `intervalo_s` (0.5): fotos do "Testar pasta" |

Opções de movimento: `area_minima_porcentagem` (0.4), `periodico_s` (10), `max_fotos_s` (2), `quadros_aquecimento` (30).

### `canal_esp32`
| `tipo` | Opções |
|---|---|
| `serial` | `portas` (`{ torre1: /dev/ttyUSB0 }`, ou `porta:` pra um só), `baud` (115200) |
| `mqtt` | `broker` (localhost), `porta` (1883), `usuario`, `senha`, `id_cliente` (vigia-pi) |
| `webapp` | `intervalo_s` (0.5): ESP32 virtual no dashboard |
| `vazio` | — |

Pra `serial` e `mqtt`: `espera_ack_s` (1.0), `max_reenvios` (2), `sem_status_s` (90).

### `memoria`
`pasta` (memoria) · `salvar_foto` (true) · `max_fotos` (5000) · `intervalo_aguardando_s` (10)

### `webapp`
`ativado` (true) · `url` (http://localhost:8000) · `enviar_foto` (`so_com_animal` \| `sempre` \| `nunca`)

---

## 13. Problemas comuns

| Sintoma | Causa provável / solução |
|---|---|
| Dashboard mostra **"processador offline"** | A janela do processador fechou ou deu erro. Veja a janela preta "VIGIA - processador" |
| Fotos ficam **na fila** no "Testar pasta" | Mesmo caso acima: o processador não está rodando |
| `não consegui abrir /dev/ttyUSB0` | Porta errada (`ls /dev/ttyUSB* /dev/ttyACM*`), cabo só de energia, ou falta o grupo `dialout` (reinicie depois do `instalar.sh`) |
| `Permission denied` na serial | `sudo usermod -aG dialout $USER` e `sudo reboot` |
| Muitos `sem ack ... reenviando` | Firmware com `delay()` longo antes do `ack recebido`, ou baud diferente de 115200 |
| O ESP32 imprime coisas e o Pi reclama | Prints de debug começando com `{`. Prefixe com `#` |
| `picamera2 não encontrado` | `sudo apt install python3-picamera2` e venv com `--system-site-packages` (o `instalar.sh` faz) |
| Cores estranhas na câmera (ave azul vira laranja) | Ordem RGB/BGR: avise, é uma linha no `picamera.py` |
| Vento/folhas disparam foto toda hora | Aumente `fonte.area_minima_porcentagem` (ex.: 1.0) |
| Mesmo bicho gera susto toda hora | Aumente o `cooldown_s` dele no `respostas.yaml` |
| `respostas.yaml: regra 'x' usa resposta 'y', que não existe` | Erro de digitação no nome da receita |
| `iniciar.bat` falha ao instalar | Disco C: cheio: o Python do treino fica no D: (`D:\espantalho_treino\venv`) |
| Gráfico não aparece | Sem internet (o Chart.js vem de CDN). O resto funciona |

---

## 14. Status e próximos passos

| | Status |
|---|---|
| Modelo (9 classes) | ✅ |
| Dashboard + teste de pasta + importar memória | ✅ |
| Processador (câmera → modelo → evento → memória) | ✅ (testado com câmera simulada) |
| Comunicação com o ESP32, lado do Pi (serial + MQTT, ack, reenvio) | ✅ (testado com ESP32 simulado) |
| Dashboard no PC (`iniciar.bat`) | ✅ testado no PC do Murilo |
| Instalação no Pi | ✅ escrita, 🔜 testar num Pi de verdade |
| **Firmware do ESP32** | 🔜 seguir o protocolo (`esp32_falso.py` é a referência) |

**Decidido pelo grupo (29/10):**
- ESP32 **no cabo USB (serial)**. O MQTT fica de reserva.
- Dashboard **separado**: copia a pasta `memoria` do Pi e usa 📥 Importar memória do Pi. Depois, se tiver rede, o Pi pode mandar direto (`webapp.ativado: true`).

**Depois:** confirmar o animal em 2 de 3 fotos (menos alarme falso), aumentar o susto se o bicho ficar, horário de silêncio, medir se o susto funcionou, editar as respostas pelo dashboard, retreinar com fotos do campo.
