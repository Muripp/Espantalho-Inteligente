"""Teste serial ativo, exclusivo do firmware vigia-receptor em simulação.

Executar só após gravar o firmware, com todos os atuadores desconectados.
"""
import argparse
import json
from pathlib import Path
import time
import uuid

import serial

from compartilhado.mensagens import agora_ms
from processador.canal_esp32.transporte import codificar, decodificar


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--porta", default="/dev/ttyUSB0")
    ap.add_argument("--atuadores-desconectados", action="store_true")
    args = ap.parse_args()
    if not args.atuadores_desconectados:
        ap.error("confirme que todos os atuadores estão desconectados")
    pasta = Path(__file__).resolve().parents[1] / "testes/pi"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / time.strftime("esp32-protocolo-%Y%m%d-%H%M%S.jsonl")
    with serial.Serial(args.porta, 115200, timeout=.2, exclusive=True) as s, destino.open("x") as log:
        def receber(aceita, segundos=5):
            fim = time.monotonic() + segundos
            while time.monotonic() < fim:
                linha = s.read_until(b"\n", 8192).decode("utf-8", "replace")
                if not linha:
                    continue
                log.write(json.dumps({"rx": linha, "ts": time.time()}) + "\n")
                log.flush()
                msg = decodificar(linha)
                if msg and aceita(msg):
                    return msg
            raise RuntimeError("Timeout aguardando mensagem esperada; consulte " + str(destino))

        def enviar(msg):
            s.write(codificar(msg))
            log.write(json.dumps({"tx": msg, "ts": time.time()}) + "\n")
            log.flush()

        # Escutar antes de enviar: não testar eventos em firmware desconhecido.
        receber(lambda m: m.get("tipo") == "status" and
                m.get("no") == "torre1" and m.get("v") == 1 and
                m.get("dados", {}).get("firmware") == "vigia-receptor-1.0.0" and
                m.get("dados", {}).get("modo") == "simulacao", segundos=40)
        enviar({"tipo": "hora", "v": 1, "ts": agora_ms()})
        receber(lambda m: m.get("tipo") == "status" and
                m.get("dados", {}).get("relogio_sincronizado") is True)
        prefixo = uuid.uuid4().hex[:8]

        def evento(sufixo, animal="ave", atraso=0):
            return {"tipo": "evento", "v": 1, "id": f"ev-{prefixo}-{sufixo}",
                    "ts": agora_ms() - atraso, "validade_ms": 2000,
                    "animal": animal, "confianca": .9, "resposta": "predador",
                    "acoes": [{"esp32": "torre1", "acao": "som", "params": {"duracao_ms": 100}}]}

        def esperar_ack(ev, status):
            msg = receber(lambda m: m.get("tipo") == "ack" and
                          m.get("dados", {}).get("evento") == ev["id"] and
                          m.get("dados", {}).get("status") == status)
            if msg["dados"].get("simulado") is not True:
                raise RuntimeError("ACK sem confirmação de simulação")
            return msg["dados"]

        ev = evento("valido")
        enviar(ev)
        esperar_ack(ev, "recebido")
        esperar_ack(ev, "executado")
        enviar(ev)
        if esperar_ack(ev, "executado").get("repetido") is not True:
            raise RuntimeError("Evento repetido não foi identificado")
        for ev, erro in [(evento("expirado", atraso=10000), "expirado_ou_futuro"),
                         (evento("humano", animal="pessoa"), "presenca_humana")]:
            enviar(ev)
            if esperar_ack(ev, "erro").get("erro") != erro:
                raise RuntimeError("Evento inválido não rejeitado como esperado")
        enviar({"tipo": "consulta", "v": 1})
        receber(lambda m: m.get("tipo") == "capacidades" and
                m.get("dados", {}).get("atuadores_habilitados") is False)
        print(f"PASSOU: ACKs, deduplicação, expiração e rejeição humana. Log: {destino}")


if __name__ == "__main__":
    main()
