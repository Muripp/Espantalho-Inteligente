"""
Fábrica de fontes de imagens.

Pra criar uma fonte nova:
  1. crie fontes/minha_fonte.py com uma classe que herda FonteDeImagens
  2. registre o nome aqui em FONTES
  3. no config.yaml: fonte: { tipo: minha_fonte, ... }
"""

from .base import FonteDeImagens


def criar_fonte(config: dict, url_webapp: str) -> FonteDeImagens:
    tipo = config.get("tipo", "webapp")
    opcoes = {k: v for k, v in config.items() if k != "tipo"}
    if tipo == "pasta":
        from .pasta import FontePasta
        return FontePasta(**opcoes)
    if tipo == "webcam":
        from .webcam import FonteWebcam
        return FonteWebcam(url_webapp=url_webapp, **opcoes)
    if tipo == "picamera":
        from .picamera import FontePicamera
        return FontePicamera(**opcoes)
    if tipo == "webapp":
        from .webapp import FonteWebapp
        return FonteWebapp(url_webapp=url_webapp, **opcoes)
    raise ValueError(f"Fonte desconhecida: {tipo!r} (use picamera, webcam, pasta ou webapp)")
