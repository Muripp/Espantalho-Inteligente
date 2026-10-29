"""
Fonte que pega as fotos enviadas pelo webapp (botão "Testar pasta" do dashboard).

O processador pergunta ao webapp: GET /api/simulador/proxima-imagem
  - 200 + JSON com a foto em base64 -> devolve a imagem
  - 204 (fila vazia)                -> devolve None e só pergunta de novo depois de `intervalo_s`
"""

import base64
import logging
import time
from typing import Optional

import cv2
import numpy as np
import requests

from compartilhado.mensagens import ImagemInfo, ImagemRecebida

from .base import FonteDeImagens

log = logging.getLogger("fonte.webapp")


class FonteWebapp(FonteDeImagens):
    def __init__(self, url_webapp: str, intervalo_s: float = 0.5, **_):
        self.url = url_webapp.rstrip("/") + "/api/simulador/proxima-imagem"
        self.intervalo_s = intervalo_s
        self.proxima_consulta = 0.0
        self.sessao = requests.Session()
        self.avisou_offline = False

    def proxima(self) -> Optional[ImagemRecebida]:
        if time.time() < self.proxima_consulta:
            return None
        try:
            r = self.sessao.get(self.url, timeout=5)
        except requests.RequestException:
            if not self.avisou_offline:
                log.warning("webapp fora do ar (%s), tentando de novo...", self.url)
                self.avisou_offline = True
            self.proxima_consulta = time.time() + 3
            return None
        if self.avisou_offline:
            log.info("webapp voltou")
            self.avisou_offline = False

        if r.status_code == 204:
            self.proxima_consulta = time.time() + self.intervalo_s
            return None
        r.raise_for_status()
        d = r.json()
        img = cv2.imdecode(np.frombuffer(base64.b64decode(d["imagem_b64"]), np.uint8),
                           cv2.IMREAD_COLOR)
        if img is None:
            log.warning("imagem inválida: %s", d.get("arquivo"))
            return None
        info = ImagemInfo.from_dict(d["info"])
        info.largura, info.altura = img.shape[1], img.shape[0]
        return ImagemRecebida(info, img)   # tinha foto: pergunta de novo logo em seguida
