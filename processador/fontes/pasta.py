"""
Fonte que lê cada imagem de uma pasta, uma vez só.

modo: camera (padrão) -> finge ser a câmera do campo: cooldown vale, eventos vão pra memória
      teste           -> cada foto é independente (sem cooldown), como o "Testar pasta" do dashboard
"""

import logging
import os
from typing import Optional

import cv2

from compartilhado.mensagens import ImagemInfo, ImagemRecebida, agora_ms, novo_id

from .base import FonteDeImagens

EXTENSOES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
log = logging.getLogger("fonte.pasta")


class FontePasta(FonteDeImagens):
    def __init__(self, pasta: str, modo: str = "camera", **_):
        self.pasta = pasta
        self.modo = modo
        self.arquivos = sorted(
            os.path.join(pasta, a) for a in os.listdir(pasta) if a.lower().endswith(EXTENSOES)
        )
        self.lote = novo_id("pasta") if modo == "teste" else None
        log.info("%d imagens em %s (modo %s)", len(self.arquivos), pasta, modo)

    def proxima(self) -> Optional[ImagemRecebida]:
        while self.arquivos:
            caminho = self.arquivos.pop(0)
            img = cv2.imread(caminho)
            if img is None:
                log.warning("não consegui abrir %s", caminho)
                continue
            info = ImagemInfo(
                id=novo_id("img"), ts=agora_ms(), origem="pasta",
                gatilho="teste" if self.lote else "movimento",
                arquivo=os.path.basename(caminho),
                data_arquivo=int(os.path.getmtime(caminho) * 1000),
                lote=self.lote, largura=img.shape[1], altura=img.shape[0],
            )
            return ImagemRecebida(info, img)
        return None

    @property
    def terminou(self) -> bool:
        return not self.arquivos
