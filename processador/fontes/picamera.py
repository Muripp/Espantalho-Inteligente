"""
Fonte: câmera oficial do Raspberry Pi (Camera Module 2/3, HQ, NoIR...) via picamera2.

- picamera2 já vem no Raspberry Pi OS (Bookworm). Ele NÃO instala pelo pip:
  o venv precisa ser criado com --system-site-packages (o instalar.sh faz isso).
- Captura em 1280x720 em formato "RGB888", que no picamera2 já sai na ordem BGR do OpenCV.
- Só entrega foto quando o GatilhoMovimento manda (movimento, periódico ou pedido do PIR).
- `rotacao: 180` se a câmera estiver de cabeça pra baixo.

    fonte:
      tipo: picamera
      largura: 1280
      altura: 720
      rotacao: 0                    # 0 | 180
      area_minima_porcentagem: 0.4  # quanto precisa mexer
      periodico_s: 10               # foto de tempos em tempos mesmo parado
"""

import logging
import time
from typing import Optional

import cv2

from compartilhado.mensagens import ImagemInfo, ImagemRecebida, agora_ms, novo_id

from .base import FonteDeImagens
from .movimento import GatilhoMovimento

log = logging.getLogger("fonte.picamera")


class FontePicamera(FonteDeImagens):
    def __init__(self, largura=1280, altura=720, rotacao=0, quadros_s=10, **opcoes_gatilho):
        try:
            from picamera2 import Picamera2
        except ImportError as e:
            raise RuntimeError(
                "picamera2 não encontrado. No Raspberry Pi OS: sudo apt install python3-picamera2 "
                "e crie o venv com --system-site-packages (o raspberry/instalar.sh já faz isso)."
            ) from e
        self.cam = Picamera2()
        cfg = self.cam.create_video_configuration(
            main={"size": (int(largura), int(altura)), "format": "RGB888"},
            controls={"FrameRate": quadros_s},
        )
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(1.0)                   # a câmera acerta exposição/branco no primeiro segundo
        self.rotacao = int(rotacao)
        self.gatilho = GatilhoMovimento(**opcoes_gatilho)
        log.info("Picamera ligada em %dx%d", largura, altura)

    def pedir_foto(self, gatilho: str) -> None:
        self.gatilho.pedir(gatilho)

    def proxima(self) -> Optional[ImagemRecebida]:
        quadro = self.cam.capture_array("main")      # espera o próximo quadro (~1/quadros_s)
        if self.rotacao == 180:
            quadro = cv2.rotate(quadro, cv2.ROTATE_180)
        g = self.gatilho.avaliar(quadro)
        if not g:
            return None
        info = ImagemInfo(id=novo_id("img"), ts=agora_ms(), origem="picamera", gatilho=g,
                          largura=quadro.shape[1], altura=quadro.shape[0])
        return ImagemRecebida(info, quadro.copy())

    def fechar(self) -> None:
        self.cam.stop()
        self.cam.close()
