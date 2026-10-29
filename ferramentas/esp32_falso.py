"""
ESP32 FALSO: um programa que se comporta como o firmware do ESP32 deveria se comportar.

Serve pra:
  - testar o processador sem o ESP32 pronto
  - servir de REFERÊNCIA pra quem vai programar o firmware (a lógica é a mesma)

O que ele faz (igual ao firmware de verdade):
  1. ao ligar: manda "capacidades" e "status"
  2. recebe "evento" -> confere validade -> ignora repetido -> responde ack "recebido"
     -> "executa" as ações (aqui só imprime e espera a duração) -> ack "executado"
  3. a cada 30 s: manda "status" (estou vivo)
  4. (opcional) simula o PIR: manda "sensor" de tempos em tempos

Usos (de dentro da pasta vigia/):
  python ferramentas/esp32_falso.py --serial COM5                 # porta serial (ex.: par virtual com com0com)
  python ferramentas/esp32_falso.py --pty                         # Linux/Pi: cria uma porta virtual e mostra o caminho
  python ferramentas/esp32_falso.py --mqtt localhost              # pelo broker MQTT
Opções de teste:
  --nome torre1        nome deste ESP32
  --perder 1           ignora os N primeiros eventos (testa o reenvio do Pi)
  --perder-ack 1       executa mas não confirma os N primeiros (testa o "repetido")
  --pir 20             manda "PIR viu movimento" a cada 20 s
  --rapido             não espera a duração das ações
"""

import argparse
import json
import os
import sys
import threading
import time

VERSAO = 1


class ESP32Falso:
    def __init__(self, nome, perder=0, rapido=False, perder_ack=0):
        self.nome = nome
        self.perder = perder
        self.perder_ack = perder_ack
        self.rapido = rapido
        self.vistos = []               # últimos ids de evento (pra ignorar repetidos)
        self.diferenca_relogio = 0     # ajustada pela mensagem "hora" do Pi
        self.inicio = time.time()
        self.saida = None              # função que manda uma linha pro Pi

    def agora_ms(self):
        return int(time.time() * 1000) + self.diferenca_relogio

    def mandar(self, tipo, dados):
        msg = {"tipo": tipo, "v": VERSAO, "no": self.nome, "ts": self.agora_ms(), "dados": dados}
        self.saida(tipo, json.dumps(msg, separators=(",", ":")))

    def ao_ligar(self):
        self.mandar("capacidades", {"acoes": ["som", "led", "rele:1", "parar"], "firmware": "falso-1.0"})
        self.status()

    def status(self):
        self.mandar("status", {"firmware": "falso-1.0", "uptime_s": int(time.time() - self.inicio),
                               "rssi": -55})

    def chegou(self, linha):
        try:
            msg = json.loads(linha)
        except json.JSONDecodeError:
            print(f"   [?] linha inválida: {linha[:80]!r}")
            return
        tipo = msg.get("tipo")
        if tipo == "hora":
            self.diferenca_relogio = msg["ts"] - int(time.time() * 1000)
            print(f"   [hora] relógio acertado (diferença {self.diferenca_relogio} ms)")
            return
        if tipo != "evento":
            print(f"   [?] tipo desconhecido: {tipo}")
            return

        ev_id = msg.get("id")
        # 1. repetido? (o Pi reenvia se o ack se perder) -> só confirma de novo, NÃO executa
        if ev_id in self.vistos:
            print(f"<- evento {ev_id} REPETIDO: só confirmo de novo, não executo")
            self.mandar("ack", {"evento": ev_id, "status": "executado", "repetido": True})
            return
        # 2. simula perda (pra testar o reenvio)
        if self.perder > 0:
            self.perder -= 1
            print(f"<- evento {ev_id}  ** fingindo que não chegou (teste de reenvio) **")
            return
        # 3. validade: chegou atrasado demais? (só se o relógio já foi acertado)
        atraso = self.agora_ms() - msg.get("ts", self.agora_ms())
        if self.diferenca_relogio and atraso > msg.get("validade_ms", 2000):
            print(f"<- evento {ev_id} atrasado {atraso} ms: descartado")
            self.mandar("ack", {"evento": ev_id, "status": "erro", "erro": "expirado"})
            return

        self.vistos = (self.vistos + [ev_id])[-20:]
        if not self.perder_ack:
            self.mandar("ack", {"evento": ev_id, "status": "recebido"})
        print(f"<- evento {ev_id}: {msg.get('animal')} ({msg.get('confianca', 0):.0%}) "
              f"-> resposta '{msg.get('resposta')}'")
        # 4. executa as ações em ordem (no firmware: tocar som, ligar relé...)
        for a in msg.get("acoes", []):
            p = a.get("params", {})
            print(f"     executando {a['acao']:<5} {p}")
            if a["acao"] == "rele":
                p["duracao_ms"] = min(p.get("duracao_ms", 0), 10000)   # trava de segurança
            if not self.rapido:
                time.sleep(min(p.get("duracao_ms", 0), 5000) / 1000)
        if self.perder_ack > 0:
            self.perder_ack -= 1
            print(f"     ** executei, mas fingindo que o ack se perdeu (teste de repetido) **")
            return
        self.mandar("ack", {"evento": ev_id, "status": "executado"})


# ------------------------------------------------------------------ transportes
def rodar_serial(esp, porta=None, pty=False, pir=0):
    if pty:
        import tty
        mestre, escravo = os.openpty()
        tty.setraw(escravo)              # sem eco e sem traduzir \n (senão o Pi recebe de volta o que mandou)
        caminho = os.ttyname(escravo)
        print(f"Porta virtual criada: {caminho}")
        print(f"  -> no config do processador:  canal_esp32: {{ tipo: serial, portas: {{ {esp.nome}: {caminho} }} }}")
        ler = lambda: os.read(mestre, 4096)
        escrever = lambda b: os.write(mestre, b)
    else:
        import serial
        s = serial.Serial(porta, 115200, timeout=0.1)
        print(f"Porta {porta} aberta")
        ler = lambda: s.read(4096)
        escrever = lambda b: s.write(b)

    trava = threading.Lock()

    def saida(_tipo, linha):
        with trava:
            escrever((linha + "\n").encode())
    esp.saida = saida
    esp.ao_ligar()
    laços_em_paralelo(esp, pir)
    buf = b""
    while True:
        buf += ler()
        while b"\n" in buf:
            linha, buf = buf.split(b"\n", 1)
            if linha.strip():
                esp.chegou(linha.decode("utf-8", "replace"))


def rodar_mqtt(esp, broker, porta=1883, pir=0):
    import paho.mqtt.client as mqtt
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"esp32-{esp.nome}")
    except AttributeError:
        c = mqtt.Client(client_id=f"esp32-{esp.nome}")
    # "testamento": se cair sem avisar, o broker publica isto no lugar dele
    c.will_set(f"vigia/{esp.nome}/status", json.dumps({"tipo": "offline", "no": esp.nome}),
               qos=1, retain=True)

    def conectou(cli, *_):
        cli.subscribe(f"vigia/{esp.nome}/evento", qos=1)
        cli.subscribe("vigia/hora", qos=1)
        print(f"conectado no broker {broker}:{porta} como {esp.nome}")
        esp.ao_ligar()
    c.on_connect = conectou
    c.on_message = lambda _c, _u, m: esp.chegou(m.payload.decode())
    esp.saida = lambda tipo, linha: c.publish(f"vigia/{esp.nome}/{tipo}", linha, qos=1,
                                              retain=tipo in ("status", "capacidades"))
    c.connect(broker, porta, keepalive=30)
    laços_em_paralelo(esp, pir)
    c.loop_forever()


def laços_em_paralelo(esp, pir):
    def vivo():
        while True:
            time.sleep(30)
            esp.status()
    threading.Thread(target=vivo, daemon=True).start()
    if pir:
        def sensor():
            while True:
                time.sleep(pir)
                print("-> PIR: movimento!")
                esp.mandar("sensor", {"sensor": "pir1", "valor": 1})
        threading.Thread(target=sensor, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description="ESP32 falso do VIGIA")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--serial", metavar="PORTA", help="ex.: COM5 ou /dev/ttyUSB0")
    g.add_argument("--pty", action="store_true", help="cria uma porta serial virtual (Linux/Pi)")
    g.add_argument("--mqtt", metavar="BROKER", help="ex.: localhost")
    ap.add_argument("--porta-mqtt", type=int, default=1883)
    ap.add_argument("--nome", default="torre1")
    ap.add_argument("--perder", type=int, default=0, help="ignora os N primeiros eventos")
    ap.add_argument("--perder-ack", type=int, default=0,
                    help="executa os N primeiros eventos mas não confirma (testa evento repetido)")
    ap.add_argument("--pir", type=float, default=0, help="manda sensor PIR a cada N segundos")
    ap.add_argument("--rapido", action="store_true", help="não espera a duração das ações")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    esp = ESP32Falso(a.nome, a.perder, a.rapido, a.perder_ack)
    try:
        if a.mqtt:
            rodar_mqtt(esp, a.mqtt, a.porta_mqtt, a.pir)
        else:
            rodar_serial(esp, a.serial, a.pty, a.pir)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
