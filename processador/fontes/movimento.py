"""
Decide QUANDO uma câmera ao vivo deve entregar uma foto pro modelo.
Usado pela webcam e pela Picamera (mesma lógica nas duas).

Entrega foto quando:
  - "movimento": mais de `area_minima_porcentagem` % da imagem mexeu
  - "periodico" : passou `periodico_s` segundos sem foto (pega ave pousada e parada)
  - "pir" (ou outro): alguém pediu com pedir() — ex.: o sensor PIR do ESP32
Nunca mais que `max_fotos_s` fotos por segundo (o modelo leva ~0,1–0,5 s cada).
"""

import time

import cv2


class GatilhoMovimento:
    def __init__(self, area_minima_porcentagem=0.4, periodico_s=10, max_fotos_s=2,
                 quadros_aquecimento=30):
        self.fundo = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25,
                                                        detectShadows=False)
        self.area_min = area_minima_porcentagem / 100
        self.periodico_s = periodico_s
        self.intervalo_min = 1 / max_fotos_s
        self.aquecimento = quadros_aquecimento
        self.quadros = 0
        self.ultima = 0.0
        self.pedido = None

    def pedir(self, gatilho: str):
        self.pedido = gatilho

    def avaliar(self, quadro) -> str | None:
        """Recebe cada quadro da câmera. Devolve o gatilho se for pra tirar foto, senão None."""
        self.quadros += 1
        agora = time.monotonic()
        pequeno = cv2.resize(quadro, (320, 240))
        mascara = self.fundo.apply(cv2.GaussianBlur(pequeno, (5, 5), 0))

        if agora - self.ultima < self.intervalo_min:
            return None
        gatilho = None
        if self.pedido:
            gatilho, self.pedido = self.pedido, None
        elif self.quadros > self.aquecimento and cv2.countNonZero(mascara) / mascara.size >= self.area_min:
            gatilho = "movimento"
        elif agora - self.ultima >= self.periodico_s:
            gatilho = "periodico"
        if gatilho:
            self.ultima = agora
        return gatilho
