"""
Canal "ESP32 virtual": usa o webapp no lugar do ESP32, pra testar sem hardware.

  enviar()  -> POST /api/esp32-virtual/eventos   (aparece no dashboard, que responde um ack)
  receber() -> GET  /api/esp32-virtual/mensagens  (acks e sensores simulados; 204 = nada)
"""

import logging
import time
from typing import Optional

import requests

from compartilhado.mensagens import EventoESP32, MensagemESP32

from .base import CanalESP32

log = logging.getLogger("canal.webapp")


class CanalWebapp(CanalESP32):
    def __init__(self, url_webapp: str, intervalo_s: float = 0.5, **_):
        base = url_webapp.rstrip("/")
        self.url_ev = base + "/api/esp32-virtual/eventos"
        self.url_msg = base + "/api/esp32-virtual/mensagens"
        self.intervalo_s = intervalo_s
        self.proxima_consulta = 0.0
        self.sessao = requests.Session()

    def enviar(self, evento: EventoESP32) -> bool:
        try:
            r = self.sessao.post(self.url_ev, json=evento.to_dict(), timeout=3)
            r.raise_for_status()
            log.info("[ESP32 virtual] <- %s: %s -> %s", evento.id, evento.animal, evento.resposta)
            return True
        except requests.RequestException as e:
            log.warning("não consegui enviar %s: %s", evento.id, e)
            return False

    def receber(self) -> Optional[MensagemESP32]:
        if time.time() < self.proxima_consulta:
            return None
        try:
            r = self.sessao.get(self.url_msg, timeout=3)
        except requests.RequestException:
            self.proxima_consulta = time.time() + 3
            return None
        if r.status_code == 204:
            self.proxima_consulta = time.time() + self.intervalo_s
            return None
        r.raise_for_status()
        return MensagemESP32.from_dict(r.json())
