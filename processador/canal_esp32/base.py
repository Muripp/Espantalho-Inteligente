"""
Interface CanalESP32: o "fio" entre o processador e o ESP32.

São só 2 métodos: o resto do sistema conversa apenas com esta interface e não sabe
se do outro lado tem um cabo serial, o Wi-Fi (MQTT) ou o ESP32 virtual do dashboard.
Vault: "04 ESP32/Canal ESP32".
"""

from abc import ABC, abstractmethod
from typing import Optional

from compartilhado.mensagens import EventoESP32, MensagemESP32


class CanalESP32(ABC):

    @abstractmethod
    def enviar(self, evento: EventoESP32) -> bool:
        """Pi -> ESP32. Entrega o evento (animal + ações) pro meio de transporte,
        SEM TRAVAR. Devolve True se saiu, False se falhou."""

    @abstractmethod
    def receber(self) -> Optional[MensagemESP32]:
        """ESP32 -> Pi. Devolve a próxima mensagem (ack, sensor, status...) ou None,
        SEM TRAVAR."""

    def fechar(self) -> None:
        pass
