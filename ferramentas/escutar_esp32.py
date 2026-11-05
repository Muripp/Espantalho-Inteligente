"""Escuta passiva da serial; não envia bytes nem instancia CanalSerial.

Use somente com atuadores desconectados: abrir a serial pode reiniciar a placa.
"""
import argparse
import json
from pathlib import Path
import time

import serial

from processador.canal_esp32.transporte import decodificar


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--porta", default="/dev/ttyUSB0")
    ap.add_argument("--segundos", type=float, default=40)
    ap.add_argument("--atuadores-desconectados", action="store_true",
                    help="confirmação física necessária antes de abrir a porta")
    args = ap.parse_args()
    if not args.atuadores_desconectados:
        ap.error("confirme fisicamente os atuadores desconectados antes de usar esta opção")
    if args.segundos <= 0:
        ap.error("segundos deve ser positivo")
    pasta = Path(__file__).resolve().parents[1] / "testes/pi"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / time.strftime("esp32-escuta-%Y%m%d-%H%M%S.jsonl")
    # Configurar sinais antes de abrir reduz transições intencionais, mas não
    # elimina glitches do driver/adaptador ao abrir a porta.
    s = serial.Serial(port=None, baudrate=115200, timeout=.2, exclusive=True)
    s.dtr = False
    s.rts = False
    s.port = args.porta
    total = validas = 0
    try:
        with destino.open("x", encoding="utf-8") as log:
            s.open()
            inicio = time.monotonic()
            buf = b""
            while time.monotonic() - inicio < args.segundos:
                buf += s.read(min(max(s.in_waiting, 1), 4096))
                while b"\n" in buf or len(buf) > 8192:
                    if b"\n" in buf:
                        linha, buf = buf.split(b"\n", 1)
                    else:
                        linha, buf = buf, b""
                    texto = linha.decode("utf-8", errors="replace").rstrip("\r")
                    msg = decodificar(texto)
                    total += 1
                    validas += msg is not None
                    registro = {"ts": time.time(), "texto": texto, "hex": linha.hex(),
                                "mensagem": msg, "bytes_enviados": 0}
                    log.write(json.dumps(registro, ensure_ascii=False) + "\n")
                    log.flush()
                    print(texto, flush=True)
                if buf:
                    log.flush()
            if buf:
                log.write(json.dumps({"ts": time.time(), "parcial_hex": buf.hex(),
                                      "bytes_enviados": 0}) + "\n")
    except KeyboardInterrupt:
        print("Escuta interrompida.")
    finally:
        s.close()
        print(f"Linhas: {total}; JSON com tipo: {validas}; bytes enviados: 0; log: {destino}")


if __name__ == "__main__":
    main()
