"""
Fonte: câmera USB / webcam do notebook (OpenCV).
Só entrega foto quando o GatilhoMovimento manda (movimento, periódico ou pedido do PIR).
"""

import logging
import sys
import threading
import time
from typing import Optional

import cv2
import requests

from compartilhado.mensagens import ImagemInfo, ImagemRecebida, agora_ms, novo_id

from .base import FonteDeImagens
from .movimento import GatilhoMovimento

log = logging.getLogger("fonte.webcam")


class FonteWebcam(FonteDeImagens):
    def __init__(self, camera=0, largura=None, altura=None, formato=None, url_webapp=None, **opcoes_gatilho):
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(int(camera) if str(camera).isdigit() else camera, backend)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError(f"Não consegui abrir a câmera {camera}")
        if formato:
            if len(formato) != 4:
                self.cap.release()
                raise ValueError("formato deve ser um FOURCC de 4 caracteres (MJPG ou YUYV)")
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*formato))
        if largura and altura:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
        self.gatilho = GatilhoMovimento(**opcoes_gatilho)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        log.info("câmera %s aberta", camera)
        self.url_webapp = url_webapp
        self.parar = threading.Event()
        self.trava = threading.Lock()
        self.ultimo = None
        self.sequencia = 0
        self.consumido = 0
        self.thread = threading.Thread(target=self._capturar, daemon=True)
        self.thread.start()

    def _capturar(self):
        # A captura continua durante a inferência; o modelo sempre recebe o quadro mais recente.
        sessao = requests.Session()
        ultimo_envio = 0
        try:
            while not self.parar.is_set():
                ok, quadro = self.cap.read()
                if not ok:
                    with self.trava:
                        self.ultimo = None
                    self.parar.wait(0.1)
                    continue
                with self.trava:
                    self.ultimo = quadro
                    self.sequencia += 1
                agora = time.monotonic()
                if self.url_webapp and agora - ultimo_envio >= 0.1:
                    ultimo_envio = agora
                    ok, jpeg = cv2.imencode('.jpg', quadro, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ok:
                        try:
                            sessao.post(self.url_webapp.rstrip('/') + '/api/camera/quadro',
                                        data=jpeg.tobytes(), headers={'Content-Type': 'image/jpeg'}, timeout=0.5)
                        except requests.RequestException:
                            pass
        finally:
            sessao.close()
            self.cap.release()

    def pedir_foto(self, gatilho: str) -> None:
        self.gatilho.pedir(gatilho)

    def proxima(self) -> Optional[ImagemRecebida]:
        with self.trava:
            if self.ultimo is None or self.sequencia == self.consumido:
                return None
            quadro = self.ultimo.copy()
            self.consumido = self.sequencia
        g = self.gatilho.avaliar(quadro)
        if not g:
            return None
        info = ImagemInfo(id=novo_id("img"), ts=agora_ms(), origem="webcam", gatilho=g,
                          largura=quadro.shape[1], altura=quadro.shape[0])
        return ImagemRecebida(info, quadro)

    def fechar(self) -> None:
        self.parar.set()
        self.thread.join(timeout=2)
