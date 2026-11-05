# Teste USB no Raspberry Pi 4 — 29/10/2026

Execute na raiz do repositório, com uma pessoa visível diante da câmera:

```bash
.venv/bin/python -m ferramentas.testar_pessoa
```

Q ou Ctrl+C encerra e libera a câmera. A janela requer sessão gráfica acessível
e suporte Qt no OpenCV. O caminho headless foi executado e validado; a janela
gráfica ainda não foi testada nesta sessão.

Sem janela, execute por exemplo 60 inferências:

```bash
.venv/bin/python -m ferramentas.testar_pessoa --headless --frames 60
```

Sem `--frames`, o teste é contínuo. Cada execução cria `testes/pi/AAAAMMDD-HHMMSS/`
com fotografia original, imagens anotadas, `deteccoes.jsonl` e `resumo.json`.
O JSONL inclui todas as detecções acima do limiar (padrão 0,35), classes,
confianças, coordenadas, decisão e latência. `--confianca 0.10` permite investigar
candidatos fracos; a regra humana do decisor continua usando o corte de 0,45.
As fotografias e logs estão ignorados pelo Git.

O script reutiliza `FonteWebcam`, `Detector`, `Decisor` e `desenhar`. Não instancia
nenhum canal de comunicação. Se uma pessoa acima do corte do decisor não resultar
em `pessoa_perto` sem evento, o teste falha explicitamente.

## Evidências desta execução

- Debian 13 ARM64, Python 3.13.5; ambiente `.venv` existente preservado.
- OpenCV 5.0.0.93, NumPy 2.5.4, ONNX Runtime 1.31.1, PyYAML 6.0.3,
  PySerial 3.5 e Requests 2.34.2. Todos importados; `pip check` sem conflitos.
  Nenhum pacote adicional foi necessário nesta missão. OpenCV não estava
  disponível no Python do sistema, portanto não se habilitou system-site-packages.
- `v4l2-ctl` confirmou DV20 USB/uvcvideo. MJPEG: 1280×720, 640×480,
  480×320, 720×480; YUYV: 640×480 e 320×240. Dispositivo sem processo ocupando.
- Captura efetiva V4L2/MJPG, 640×480, frequência nominal negociada 25 FPS.
  30 frames de aquecimento + 12 frames inferidos, todos lidos com sucesso.
- `testes/pi/20261029-200254/captura.jpg` foi salva, relida e inspecionada:
  quadro com desenhos, sem pessoa visível; imagem íntegra e reconhecível.
  Intensidade média 159,62/255, desvio 47,35, variância Laplaciana 258,20
  (indicadores registrados, sem pretensão de certificação de qualidade).
- Modelo original `espantalho_aves.onnx` carregado no CPUExecutionProvider,
  entrada 640×640. Classes dos metadados: 0 ave, 1 cachorro, 2 porco,
  3 cavalo, 4 rato, 5 vaca, 6 gato, **7 pessoa**, 8 outro_animal.
- 12 inferências reais: média 754 ms, mediana 729 ms, intervalo 618–984 ms;
  FPS médio informado pelo loop 1,34 (captura/inferência/desenho, sem gravação).
  FPS global 1,07 incluindo aquecimento e gravação. Nenhuma detecção acima
  de 0,35, portanto nenhuma coordenada/confiança positiva a apresentar.
- Loop principal real: 16 análises, média 807 ms (622–1321 ms), todas `nada`.
  Log em `testes/pi/processador.log`. Executado com limite externo de 18 s,
  SIGINT tratado normalmente (`desligando`); código 124 é do `timeout`.
- Teste da regra humana com entradas artificiais (não são detecções visuais):
  pessoa 87%, sozinha e com ave 95%, bloqueou eventos nos dois casos.
  Executar: `.venv/bin/python -m unittest ferramentas.test_seguranca_pessoa`.
- Compilação Python e `git diff --check` passaram. Câmera liberada no final;
  serviço `vigia` permaneceu inativo. Serial não foi aberta, firmware não foi
  gravado e nenhum comando foi enviado a atuadores.

## Configuração e integração

`processador/config_pi_teste.yaml` preserva a configuração original, usa webcam
`/dev/video0`, 640×480/MJPG, canal vazio e dashboard desativado. Para o loop real:

```bash
.venv/bin/python -m processador --config processador/config_pi_teste.yaml
```

Na fonte webcam, Linux agora seleciona V4L2 explicitamente, aceita FOURCC
opcional e solicita buffer de um frame. O detector/modelo/NMS foram preservados.
Não executar `raspberry/instalar.sh` para este teste: ele configura e inicia
o serviço automaticamente e pressupõe Picamera2.

## Validação presencial humana — 20:06

Com uma pessoa colocada diante da câmera pelo usuário, o teste headless realizou
20 inferências em 50 frames capturados (30 de aquecimento). Houve detecção real
de `pessoa` em 18/20 imagens, com confianças de 65,02% a 91,57%; os dois últimos
frames não tiveram detecções acima de 35%. A imagem anotada do primeiro frame
foi inspecionada: pessoa com retângulo em (142,79)–(606,478), confiança 90,81%.
Não se deve interpretar 18/20 como medida de acurácia: é uma amostra ao vivo,
com movimento e mudança de enquadramento.

Latência média 701,97 ms, mediana 701,45 ms, FPS médio do loop 1,42;
FPS global incluindo aquecimento e gravações 1,15. Todas as imagens com pessoa
resultaram em `pessoa_perto`, nenhum evento gerado e zero comandos enviados.
Artefatos: `testes/pi/20261029-200616/` (`frame-000001.jpg`,
`deteccoes.jsonl`, `resumo.json`).

O loop principal também foi executado com a pessoa: oito análises reais,
todas `pessoa_perto`, confiança de 58% a 81%, sem eventos de acionamento.
Log: `testes/pi/processador_pessoa.log`. Encerramento por SIGINT após 10 s,
com liberação da câmera. O reconhecimento visual humano está confirmado;
continua pendente apenas validar a janela gráfica presencialmente.

## Segunda rodada presencial — 20:09–20:10

Artefatos em `testes/pi/20261029-200951/`: 50 frames lidos, 20 inferências,
18 frames com pessoa e decisão `pessoa_perto`, até sete caixas de pessoa por
frame (não é contagem validada de indivíduos). Média de inferência 1024 ms,
FPS médio do loop 1,02. Imagem `frame-000010.jpg` inspecionada com várias
pessoas na sala. Zero comandos enviados.

O primeiro frame, fortemente borrado pelo movimento, produziu falso positivo
`ave` 77,85%, com decisão local `espantou`; o segundo foi `nada`.
O script não instancia canal e não transmitiu esse evento.

O loop principal adicional (`testes/pi/processador_rodada2.log`) realizou sete
análises: seis `nada` e uma classificação incorreta `gato` 46%, que teria
selecionado `latido`. A fotografia da memória
`testes/pi/memoria/fotos/1793315438358_an-957cea3e.jpg` foi inspecionada:
pessoa muito próxima da câmera, com enquadramento parcial. O canal vazio
registrou explicitamente que não enviou o evento. Encerramento normal por SIGINT.

Esses casos mostram que a regra humana bloqueia quando o modelo reconhece
`pessoa`, mas não protege uma pessoa que o modelo deixou de reconhecer ou
classificou como animal. Não houve alteração automática de modelo ou limiares.
Antes de testes físicos, é necessário tratar esses falsos positivos e validar
as condições de enquadramento; manter canal vazio.

## Terceira rodada — 20:14

`testes/pi/20261029-201429/`: 50 frames capturados, 20 inferências,
17 frames com detecções de pessoa acima de 35%; 16 com bloqueio `pessoa_perto`.
No frame 19 a pessoa teve confiança 44,26%, abaixo do corte de segurança atual
de 45%, resultando em `nada` (sem animal válido nesse frame).
Latência média 965 ms, FPS médio do loop 1,08. Zero comandos enviados.

Houve também classificações cachorro/cavalo e ave. A imagem do frame 3 foi
inspecionada: uma fotografia de cavalo exibida em um notebook foi classificada
como cachorro 89%, enquanto pessoas reconhecidas bloquearam o evento.
Frames 17 e 18 classificaram `ave` (89,91% e 59,46%) sem pessoa reconhecida,
com decisões locais `espantou` e `aguardando`; esses frames específicos não
foram salvos pelo critério de amostragem atual, portanto não se confirmou
visualmente o objeto nessas duas detecções. Resultados completos no JSONL.
O teste terminou liberando a câmera, sem canal de comunicação.

Para integrar ao ESP32 depois, inspecionar o firmware/protocolo atual sem ações
físicas e validar JSON por linha a 115200 baud, identidade `torre1`, capacidades,
status, ACK recebido/executado, validade, deduplicação e limites das ações.
O firmware ainda não foi validado. Apresentar plano antes de qualquer gravação.
Manter canal vazio até autorização para os testes físicos.
