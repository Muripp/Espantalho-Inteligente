"""
Interface FonteDeImagens: de onde vêm as fotos.

O resto do processador só conversa com estes 3 métodos, então trocar a câmera
(pasta, webcam, webapp, Picamera...) não muda nada no resto do código.
Vault: "02 Processador (Raspberry Pi)/Fonte de imagens".
"""

from abc import ABC, abstractmethod
from typing import Optional

from compartilhado.mensagens import ImagemRecebida


class FonteDeImagens(ABC):

    @abstractmethod
    def proxima(self) -> Optional[ImagemRecebida]:
        """Entrega a próxima foto disponível, SEM TRAVAR. Se não tiver, devolve None."""

    def pedir_foto(self, gatilho: str) -> None:
        """Pede uma foto agora (ex.: o PIR do ESP32 viu movimento).
        Fontes que não tiram foto sob demanda podem ignorar."""

    def fechar(self) -> None:
        """Libera câmera/arquivos."""
