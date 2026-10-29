"""
Canal MQTT: o ESP32 fala com o Raspberry Pi pelo Wi-Fi.

O Pi roda o "broker" (Mosquitto), que é a central de mensagens. Pi e ESP32 se conectam nele.

Tópicos  ({esp32} = nome do ESP32, ex.: torre1):
  Pi    -> ESP32   vigia/{esp32}/evento        o evento (só com as ações daquele ESP32)   QoS 1
  Pi    -> todos   vigia/hora                  relógio (retido; a cada 60 s)
  ESP32 -> Pi      vigia/{esp32}/ack           confirmação de um evento                   QoS 1
  ESP32 -> Pi      vigia/{esp32}/sensor        sensor viu algo (ex.: PIR)
  ESP32 -> Pi      vigia/{esp32}/status        "estou vivo" a cada 30 s (retido)
                                               + testamento {"tipo":"offline"} se cair
  ESP32 -> Pi      vigia/{esp32}/capacidades   o que ele sabe fazer (retido)

O conteúdo de cada mensagem é o MESMO JSON da serial (ver transporte.py).

    canal_esp32:
      tipo: mqtt
      broker: localhost      # o Mosquitto roda no próprio Pi
      porta: 1883
      usuario: vigia         # opcional
      senha: ...             # opcional
"""

import json
import logging
import queue
import time
from typing import Optional

from .transporte import CanalTransporte, codificar, decodificar, mensagem_hora

log = logging.getLogger("canal.mqtt")
PREFIXO = "vigia"


class CanalMQTT(CanalTransporte):
    def __init__(self, broker: str = "localhost", porta: int = 1883, usuario: str = None,
                 senha: str = None, id_cliente: str = "vigia-pi", **opcoes):
        super().__init__(**opcoes)
        import paho.mqtt.client as mqtt     # só precisa instalar se usar este canal
        self.fila = queue.Queue()
        self.conectado = False
        self.ultima_hora = 0.0
        try:                                # paho-mqtt 2.x
            self.cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=id_cliente)
        except AttributeError:              # paho-mqtt 1.x
            self.cliente = mqtt.Client(client_id=id_cliente)
        if usuario:
            self.cliente.username_pw_set(usuario, senha)
        self.cliente.on_connect = self._conectou
        self.cliente.on_disconnect = self._desconectou
        self.cliente.on_message = self._chegou
        self.cliente.reconnect_delay_set(1, 10)
        self.cliente.connect_async(broker, int(porta), keepalive=30)
        self.cliente.loop_start()           # thread do paho cuida da rede e reconecta sozinha
        log.info("conectando no broker %s:%s ...", broker, porta)

    # ---- callbacks do paho (rodam na thread dele: só colocam na fila)
    def _conectou(self, cliente, _u, _f, codigo, *_):
        falhou = codigo.is_failure if hasattr(codigo, "is_failure") else codigo != 0
        if falhou:
            log.error("broker recusou a conexão: %s", codigo)
            return
        self.conectado = True
        for sub in ("ack", "sensor", "status", "capacidades"):
            cliente.subscribe(f"{PREFIXO}/+/{sub}", qos=1)
        log.info("conectado no broker")

    def _desconectou(self, *_):
        if self.conectado:
            log.warning("desconectado do broker (reconectando...)")
        self.conectado = False

    def _chegou(self, _c, _u, m):
        partes = m.topic.split("/")
        if len(partes) != 3:
            return
        msg = decodificar(m.payload.decode("utf-8", errors="replace"))
        if msg:
            self.fila.put((partes[1], msg))

    # ---- o que o CanalTransporte pede
    def _mandar(self, esp32: str, msg: dict) -> bool:
        if not self.conectado:
            log.warning("sem conexão com o broker: evento pra %s fica pro reenvio", esp32)
            return False
        if msg.get("tipo") == "hora":
            topico, retido = f"{PREFIXO}/hora", True
        else:
            topico, retido = f"{PREFIXO}/{esp32}/{msg['tipo']}", False
        r = self.cliente.publish(topico, codificar(msg).rstrip(b"\n"), qos=1, retain=retido)
        return r.rc == 0

    def _pegar(self) -> Optional[tuple]:
        if self.conectado and time.monotonic() - self.ultima_hora > 60:
            self.ultima_hora = time.monotonic()
            self._mandar("*", mensagem_hora())
        try:
            return self.fila.get_nowait()
        except queue.Empty:
            return None

    def fechar(self) -> None:
        self.cliente.loop_stop()
        self.cliente.disconnect()
