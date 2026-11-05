"""Teste real de webcam + Detector + Decisor; nunca cria um canal ESP32.

Na raiz: .venv/bin/python -m ferramentas.testar_pessoa --headless --frames 20
Sem --frames, executa até Q ou Ctrl+C. Artefatos privados em testes/pi/.
"""

import argparse
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np
import yaml

from processador.decisor import Decisor
from processador.detector import Detector
from processador.fontes.webcam import FonteWebcam
from processador.publicador import desenhar

RAIZ = Path(__file__).resolve().parents[1]


def salvar(caminho, imagem):
    if not cv2.imwrite(str(caminho), imagem):
        raise RuntimeError(f"Falha ao salvar {caminho}")
    recarregada = cv2.imread(str(caminho))
    if recarregada is None or recarregada.shape != imagem.shape:
        raise RuntimeError(f"Imagem gravada inválida: {caminho}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=RAIZ / "processador/config_pi_teste.yaml")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--frames", type=int, default=0, help="0: contínuo")
    ap.add_argument("--confianca", type=float, default=0.35)
    ap.add_argument("--saida", type=Path, default=RAIZ / "testes/pi")
    args = ap.parse_args()
    if args.frames < 0 or not 0 < args.confianca < 1:
        ap.error("frames deve ser >= 0 e confiança entre 0 e 1")
    cfg = yaml.safe_load(args.config.read_text())
    if cfg["fonte"]["tipo"] != "webcam" or cfg["canal_esp32"]["tipo"] != "vazio":
        ap.error("teste exige fonte webcam e canal vazio")
    pasta = args.saida / time.strftime("%Y%m%d-%H%M%S")
    pasta.mkdir(parents=True, exist_ok=False)
    decisor = Decisor(str(RAIZ / "processador" / cfg["respostas"]))
    detector = Detector(str(RAIZ / "processador" / cfg["modelo"]), args.confianca)
    meta = detector.sessao.get_modelmeta().custom_metadata_map
    if "pessoa" not in detector.classes.values():
        raise RuntimeError(f"Modelo sem classe pessoa: {detector.classes}")
    fonte = None
    tempos, pessoas, capturas = [], 0, 0
    inicio = time.perf_counter()
    grafico = not args.headless and bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    resumo = {"classes": detector.classes, "metadados": meta, "canal": "nenhum", "confianca_min": args.confianca}
    print(json.dumps(resumo, ensure_ascii=False), flush=True)
    try:
        opcoes = {k: v for k, v in cfg["fonte"].items() if k != "tipo"}
        fonte = FonteWebcam(**opcoes)
        cap = fonte.cap
        # Aquecer exposição e verificar múltiplos frames reais antes da inferência.
        for _ in range(30):
            ok, img = cap.read()
            if not ok or img is None or img.size == 0:
                raise RuntimeError("Falha na leitura da webcam durante aquecimento")
            capturas += 1
        if img.shape[:2] != (opcoes["altura"], opcoes["largura"]):
            raise RuntimeError(f"Resolução inesperada: {img.shape}")
        salvar(pasta / "captura.jpg", img)
        resumo["camera"] = {"backend": cap.getBackendName(), "resolucao": list(img.shape),
                            "fps_camera": cap.get(cv2.CAP_PROP_FPS),
                            "fourcc": "".join(chr((int(cap.get(cv2.CAP_PROP_FOURCC)) >> (8*i)) & 255) for i in range(4)),
                            "media": float(img.mean()), "desvio": float(img.std()),
                            "nitidez_laplaciano": float(cv2.Laplacian(img, cv2.CV_64F).var())}
        with (pasta / "deteccoes.jsonl").open("w") as log:
            while not args.frames or len(tempos) < args.frames:
                t0 = time.perf_counter()
                ok, img = cap.read()
                if not ok or img is None or img.size == 0:
                    raise RuntimeError("Falha na captura; câmera desconectada ou ocupada")
                capturas += 1
                tdet = time.perf_counter()
                deteccoes = detector.detectar(img)
                ms = (time.perf_counter() - tdet) * 1000
                tempos.append(ms)
                decisao = decisor.decidir(deteccoes, f"teste-{len(tempos)}")
                humanos = [d for d in deteccoes if d.classe == "pessoa"]
                pessoas += bool(humanos)
                if any(d.confianca >= decisor.corte("pessoa") for d in humanos):
                    if decisao.decisao != "pessoa_perto" or decisao.evento is not None:
                        raise RuntimeError("Regra de segurança humana falhou")
                for d in humanos:
                    print(f"PESSOA DETECTADA | Confiança: {d.confianca:.0%}", flush=True)
                anotada = desenhar(img, deteccoes)
                fps = 1 / (time.perf_counter() - t0)
                cv2.putText(anotada, f"{ms:.0f} ms | {fps:.2f} FPS", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
                registro = {"frame": len(tempos), "ts": time.time(), "inferencia_ms": ms,
                            "fps_loop": fps, "deteccoes": [d.to_dict() for d in deteccoes],
                            "decisao": decisao.decisao, "evento_gerado": decisao.evento is not None,
                            "comandos_enviados": 0}
                log.write(json.dumps(registro, ensure_ascii=False) + "\n")
                log.flush()
                print(json.dumps(registro, ensure_ascii=False), flush=True)
                # Amostra periódica, última imagem e cada frame com pessoa.
                if len(tempos) == 1 or humanos or len(tempos) % 10 == 0:
                    salvar(pasta / f"frame-{len(tempos):06d}.jpg", anotada)
                salvar(pasta / "ultima.jpg", anotada)
                if grafico:
                    try:
                        cv2.imshow("Espantalho - Q para sair", anotada)
                        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                            break
                    except cv2.error as erro:
                        print(f"GUI indisponível; continuando headless: {erro}", flush=True)
                        grafico = False
    except KeyboardInterrupt:
        print("Encerrado pelo usuário.", flush=True)
    except Exception as erro:
        resumo["erro"] = str(erro)
        raise
    finally:
        if fonte is not None:
            fonte.fechar()
        if grafico:
            cv2.destroyAllWindows()
        resumo.update(frames_lidos=capturas, inferencias=len(tempos), frames_com_pessoa=pessoas,
                      inferencia_media_ms=float(np.mean(tempos)) if tempos else None,
                      inferencia_mediana_ms=float(np.median(tempos)) if tempos else None,
                      fps_total=len(tempos) / (time.perf_counter() - inicio), comandos_enviados=0)
        (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2))
        print(f"Resultados: {pasta}", flush=True)


if __name__ == "__main__":
    main()
