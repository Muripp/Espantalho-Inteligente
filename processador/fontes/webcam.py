"""
Fonte: câmera USB / webcam do notebook (OpenCV).
Só entrega foto quando o GatilhoMovimento manda (movimento, periódico ou pedido do PIR).
"""

import logging
from typing import Optional

import cv2

from compartilhado.mensagens import ImagemInfo, ImagemRecebida, agora_ms, novo_id

from .base import FonteDeImagens
from .movimento import GatilhoMovimento

log = logging.getLogger("fonte.webcam")


class FonteWebcam(FonteDeImagens):
    def __init__(self, camera=0, largura=None, altura=None, **opcoes_gatilho):
        self.cap = cv2.VideoCapture(int(camera) if str(camera).isdigit() else camera)
        if not self.cap.isOpened():
            raise RuntimeError(f"Não consegui abrir a câmera {camera}")
        if largura and altura:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
        self.gatilho = GatilhoMovimento(**opcoes_gatilho)
        log.info("câmera %s aberta", camera)

    def pedir_foto(self, gatilho: str) -> None:
        self.gatilho.pedir(gatilho)

    def proxima(self) -> Optional[ImagemRecebida]:
        ok, quadro = self.cap.read()
        if not ok:
            return None
        g = self.gatilho.avaliar(quadro)
        if not g:
            return None
        info = ImagemInfo(id=novo_id("img"), ts=agora_ms(), origem="webcam", gatilho=g,
                          largura=quadro.shape[1], altura=quadro.shape[0])
        return ImagemRecebida(info, quadro)

    def fechar(self) -> None:
        self.cap.release()
