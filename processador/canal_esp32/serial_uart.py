"""
Canal SERIAL: o ESP32 ligado no Raspberry Pi por cabo USB (ou pelos pinos TX/RX da UART).

  - 115200 baud, 8N1
  - cada mensagem é UMA linha de JSON terminada em "\\n" (ver transporte.py)
  - dá pra ter vários ESP32, um por porta:
        canal_esp32:
          tipo: serial
          portas: { torre1: /dev/ttyUSB0, bomba1: /dev/ttyUSB1 }
  - se o cabo sair, tenta reconectar a cada 3 s sozinho
  - linhas que não começam com "{" (prints de debug do ESP32) são ignoradas

No Windows a porta é tipo "COM3"; no Raspberry Pi, "/dev/ttyUSB0" (USB) ou "/dev/serial0" (pinos).
"""

import logging
import time
from typing import Optional

from .transporte import CanalTransporte, codificar, decodificar

log = logging.getLogger("canal.serial")


class CanalSerial(CanalTransporte):
    def __init__(self, portas: dict = None, porta: str = None, baud: int = 115200, **opcoes):
        super().__init__(**opcoes)
        import serial                       # pyserial (só precisa instalar se usar este canal)
        self._serial = serial
        if not portas:
            portas = {"torre1": porta or "/dev/ttyUSB0"}
        self.portas = dict(portas)          # esp32 -> caminho da porta
        self.baud = baud
        self.abertas = {}                   # esp32 -> objeto Serial
        self.buffers = {}                   # esp32 -> bytes ainda sem "\n"
        self.proxima_tentativa = {}         # esp32 -> quando tentar abrir de novo
        for esp32 in self.portas:
            self._abrir(esp32)

    # ---- conexão
    def _abrir(self, esp32: str) -> bool:
        if esp32 in self.abertas:
            return True
        if time.monotonic() < self.proxima_tentativa.get(esp32, 0):
            return False
        caminho = self.portas[esp32]
        try:
            s = self._serial.Serial(caminho, self.baud, timeout=0, write_timeout=0.5)
            self.abertas[esp32] = s
            self.buffers[esp32] = b""
            log.info("porta %s aberta (%s)", caminho, esp32)
            return True
        except (self._serial.SerialException, OSError) as e:
            self.proxima_tentativa[esp32] = time.monotonic() + 3
            log.warning("não consegui abrir %s (%s): %s. Tento de novo em 3 s", caminho, esp32, e)
            return False

    def _perdeu(self, esp32: str, erro):
        log.warning("perdi a porta de %s: %s", esp32, erro)
        try:
            self.abertas.pop(esp32).close()
        except Exception:
            pass
        self.proxima_tentativa[esp32] = time.monotonic() + 3

    # ---- o que o CanalTransporte pede
    def _mandar(self, esp32: str, msg: dict) -> bool:
        if esp32 not in self.portas:
            log.error("não sei em que porta fica o ESP32 %r (veja canal_esp32.portas)", esp32)
            return False
        if not self._abrir(esp32):
            return False
        try:
            self.abertas[esp32].write(codificar(msg))
            return True
        except (self._serial.SerialException, OSError) as e:
            self._perdeu(esp32, e)
            return False

    def _pegar(self) -> Optional[tuple]:
        for esp32 in list(self.portas):
            if not self._abrir(esp32):
                continue
            s = self.abertas[esp32]
            try:
                chegou = s.read(s.in_waiting or 1)
            except (self._serial.SerialException, OSError) as e:
                self._perdeu(esp32, e)
                continue
            if chegou:
                self.buffers[esp32] += chegou
                if len(self.buffers[esp32]) > 8192:        # lixo sem "\n": descarta
                    self.buffers[esp32] = b""
            while b"\n" in self.buffers.get(esp32, b""):
                linha, self.buffers[esp32] = self.buffers[esp32].split(b"\n", 1)
                msg = decodificar(linha.decode("utf-8", errors="replace"))
                if msg:
                    return esp32, msg
        return None

    def fechar(self) -> None:
        for s in self.abertas.values():
            s.close()
