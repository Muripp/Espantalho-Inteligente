"""
Canal VAZIO: não fala com ESP32 nenhum.

  enviar()  -> só escreve no terminal o evento que SERIA enviado
  receber() -> nunca chega nada

Os canais de verdade são serial_uart.py (cabo) e mqtt.py (Wi-Fi):
é só trocar `canal_esp32.tipo` no config.yaml.
"""

import json
import logging
from typing import Optional

from compartilhado.mensagens import EventoESP32, MensagemESP32

from .base import CanalESP32

log = logging.getLogger("canal.vazio")


class CanalVazio(CanalESP32):
    def __init__(self, **_):
        pass

    def enviar(self, evento: EventoESP32) -> bool:
        log.info("[ESP32] <- evento %s: %s -> %s %s (não enviado: canal vazio)",
                 evento.id, evento.animal, evento.resposta,
                 json.dumps(evento.acoes, ensure_ascii=False))
        return True

    def receber(self) -> Optional[MensagemESP32]:
        return None
