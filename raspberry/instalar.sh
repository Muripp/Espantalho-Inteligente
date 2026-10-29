#!/usr/bin/env bash
# Instala o processador do VIGIA num Raspberry Pi (Raspberry Pi OS Bookworm, 64 bits).
#
# Uso (no Pi, dentro da pasta vigia/):
#     bash raspberry/instalar.sh            # instala e liga o serviço (inicia sozinho no boot)
#     bash raspberry/instalar.sh --mqtt     # idem + instala o broker Mosquitto (ESP32 pelo Wi-Fi)
#
# Depois:
#     sudo systemctl status vigia           # está rodando?
#     journalctl -u vigia -f                # ver o log ao vivo
#     sudo systemctl restart vigia          # depois de mudar o config_pi.yaml ou o respostas.yaml
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="$(whoami)"
cd "$PASTA"
echo "== VIGIA em $PASTA (usuário $USUARIO)"

echo "== 1/5 pacotes do sistema (câmera, OpenCV, serial)"
sudo apt-get update -q
sudo apt-get install -y -q python3-venv python3-picamera2 python3-opencv python3-numpy

if [[ "${1:-}" == "--mqtt" ]]; then
  echo "== 1b/5 broker MQTT (Mosquitto)"
  sudo apt-get install -y -q mosquitto mosquitto-clients
  # aceita ESP32 da rede local (sem senha: ok numa rede só do espantalho; senão configure usuário/senha)
  echo -e "listener 1883\nallow_anonymous true" | sudo tee /etc/mosquitto/conf.d/vigia.conf > /dev/null
  sudo systemctl enable --now mosquitto
  sudo systemctl restart mosquitto
fi

echo "== 2/5 ambiente Python (usa a câmera e o OpenCV do sistema)"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r raspberry/requirements-pi.txt

echo "== 3/5 permissão pra usar a porta serial"
sudo usermod -aG dialout "$USUARIO"

echo "== 4/5 teste rápido (modelo + câmera)"
.venv/bin/python - <<'PY'
import time, sys
sys.path.insert(0, ".")
from processador.detector import Detector
d = Detector("processador/modelos/espantalho_aves.onnx", 0.35)
import numpy as np
img = np.zeros((720, 1280, 3), np.uint8)
d.detectar(img); t = time.perf_counter()
for _ in range(5): d.detectar(img)
print(f"   modelo OK: {(time.perf_counter() - t) / 5 * 1000:.0f} ms por foto neste Pi")
try:
    from picamera2 import Picamera2
    c = Picamera2(); c.close(); print("   câmera OK")
except Exception as e:
    print(f"   ATENÇÃO câmera: {e}")
PY

echo "== 5/5 serviço (liga sozinho quando o Pi ligar)"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__USUARIO__#$USUARIO#g" raspberry/vigia.service \
  | sudo tee /etc/systemd/system/vigia.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable vigia
sudo systemctl restart vigia

echo
echo "Pronto! O processador está rodando."
echo "  log ao vivo:   journalctl -u vigia -f"
echo "  memória:       $PASTA/processador/memoria/"
echo "  (se acabou de entrar no grupo 'dialout', reinicie o Pi uma vez: sudo reboot)"
