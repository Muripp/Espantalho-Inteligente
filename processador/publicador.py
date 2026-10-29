"""
Publicador: manda pro webapp o que o processador viu e fez.
Vault: "02 Processador (Raspberry Pi)/Publicador".

- publicar()           -> POST /api/analises             (ResultadoAnalise)
- atualizar_evento()   -> POST /api/eventos-esp32/{id}/status (ack do ESP32)
Se o webapp estiver fora do ar, guarda em `pendentes/` e reenvia depois.
O processador NUNCA para por causa do webapp.
"""

import base64
import json
import logging
import os
import time

import cv2
import requests

from compartilhado.mensagens import ResultadoAnalise

log = logging.getLogger("publicador")

CORES = {  # BGR
    "ave": (0, 200, 255), "cachorro": (0, 80, 255), "porco": (200, 0, 255),
    "cavalo": (40, 120, 200), "rato": (90, 90, 90), "vaca": (255, 255, 0),
    "gato": (255, 120, 200), "pessoa": (0, 200, 0), "outro_animal": (200, 200, 200),
}


def desenhar(img, deteccoes):
    """Devolve uma cópia da imagem com as caixas e rótulos desenhados."""
    img = img.copy()
    esp = max(2, round(max(img.shape[:2]) / 400))
    for d in deteccoes:
        x1, y1, x2, y2 = d.caixa
        cor = CORES.get(d.classe, (255, 255, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), cor, esp)
        txt = f"{d.classe} {d.confianca:.0%}"
        esc = esp * 0.35
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, esc, esp)
        cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), cor, -1)
        cv2.putText(img, txt, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), esp)
    return img


def jpeg_b64(img, lado_max=800):
    h, w = img.shape[:2]
    esc = lado_max / max(h, w)
    if esc < 1:
        img = cv2.resize(img, (round(w * esc), round(h * esc)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return base64.b64encode(buf).decode() if ok else None


class Publicador:
    def __init__(self, url_webapp: str, enviar_foto: str = "so_com_animal",
                 pasta_pendentes: str = "pendentes"):
        base = url_webapp.rstrip("/")
        self.url_analises = base + "/api/analises"
        self.url_status = base + "/api/eventos-esp32/{}/status"
        self.enviar_foto = enviar_foto
        self.pendentes = pasta_pendentes
        os.makedirs(self.pendentes, exist_ok=True)
        self.sessao = requests.Session()
        self.proximo_reenvio = 0.0

    def precisa_foto(self, resultado: ResultadoAnalise) -> bool:
        if resultado.imagem.lote:            # teste de pasta: sempre manda a foto
            return True
        if self.enviar_foto == "sempre":
            return True
        if self.enviar_foto == "nunca":
            return False
        return resultado.decisao != "nada"

    def publicar(self, resultado: ResultadoAnalise, imagem_anotada=None):
        if imagem_anotada is not None and self.precisa_foto(resultado):
            resultado.foto_jpeg_b64 = jpeg_b64(imagem_anotada)
        dados = resultado.to_dict()
        if not self._post(self.url_analises, dados):
            caminho = os.path.join(self.pendentes, f"{resultado.ts}_{resultado.id}.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"url": self.url_analises, "dados": dados}, f)
            log.warning("webapp fora do ar: análise %s guardada em %s", resultado.id, caminho)

    def atualizar_evento(self, id_evento: str, status: str, dados: dict):
        self._post(self.url_status.format(id_evento), {"status": status, **dados})

    def reenviar_pendentes(self):
        """Chamado no loop; tenta reenviar no máximo a cada 30 s."""
        if time.time() < self.proximo_reenvio:
            return
        self.proximo_reenvio = time.time() + 30
        for nome in sorted(os.listdir(self.pendentes)):
            caminho = os.path.join(self.pendentes, nome)
            with open(caminho, encoding="utf-8") as f:
                item = json.load(f)
            if not self._post(item["url"], item["dados"]):
                return
            os.remove(caminho)
            log.info("pendente reenviado: %s", nome)

    def _post(self, url, dados) -> bool:
        try:
            r = self.sessao.post(url, json=dados, timeout=5)
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            log.debug("POST %s falhou: %s", url, e)
            return False
