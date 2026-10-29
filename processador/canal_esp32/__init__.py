"""
Fábrica de canais do ESP32.

  vazio   só mostra no terminal o que mandaria (sem hardware)
  webapp  ESP32 virtual no dashboard (sem hardware)
  serial  ESP32 no cabo USB/UART do Pi            <- canal real
  mqtt    ESP32 pelo Wi-Fi, via broker Mosquitto   <- canal real

Pra criar outro: siga canal_esp32/base.py (ou transporte.py, se for um fio novo) e registre aqui.
"""

from .base import CanalESP32


def criar_canal(config: dict, url_webapp: str) -> CanalESP32:
    tipo = config.get("tipo", "vazio")
    opcoes = {k: v for k, v in config.items() if k != "tipo"}
    if tipo == "vazio":
        from .vazio import CanalVazio
        return CanalVazio(**opcoes)
    if tipo == "webapp":
        from .webapp import CanalWebapp
        return CanalWebapp(url_webapp=url_webapp, **opcoes)
    if tipo == "serial":
        from .serial_uart import CanalSerial
        return CanalSerial(**opcoes)
    if tipo == "mqtt":
        from .mqtt import CanalMQTT
        return CanalMQTT(**opcoes)
    raise ValueError(f"Canal desconhecido: {tipo!r} (use vazio, webapp, serial ou mqtt)")
