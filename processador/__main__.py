"""
Processador do VIGIA: o loop principal.
Vault: "02 Processador (Raspberry Pi)/Processador".

Fluxo (combinado com o grupo):
    fica vendo a câmera -> processa a imagem no modelo ->
    viu animal? -> anota um EVENTO -> manda pro ESP32 (animal + resposta do banco de respostas)
                                   -> guarda na memória própria (memoria/eventos.jsonl)
                                   -> (opcional) publica no dashboard

Rodar (de dentro da pasta vigia/):
    python -m processador
    python -m processador --config processador/config.yaml
"""

import argparse
import copy
import logging
import os
import sys
import time

import yaml

from compartilhado.mensagens import ResultadoAnalise, EventoESP32

from .canal_esp32 import criar_canal
from .decisor import Decisor
from .detector import Detector
from .fontes import criar_fonte
from .memoria import Memoria
from .publicador import Publicador, desenhar

PASTA = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("processador")


def caminho(p):
    return p if os.path.isabs(p) else os.path.join(PASTA, p)


def main():
    ap = argparse.ArgumentParser(description="Processador do VIGIA")
    ap.add_argument("--config", default=os.path.join(PASTA, "config.yaml"))
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logging.basicConfig(level=cfg.get("log", "INFO"),
                        format="%(asctime)s %(levelname)-7s %(name)-14s %(message)s",
                        datefmt="%H:%M:%S")

    url = cfg["webapp"]["url"]
    decisor = Decisor(caminho(cfg.get("respostas", "respostas.yaml")))
    detector = Detector(caminho(cfg["modelo"]), confianca_min=decisor.menor_corte)
    nome_modelo = os.path.basename(cfg["modelo"])
    fonte = criar_fonte(cfg.get("fonte", {}), url)
    canal = criar_canal(cfg.get("canal_esp32", {}), url)
    cfg_mem = cfg.get("memoria", {})
    memoria = Memoria(caminho(cfg_mem.get("pasta", "memoria")), cfg_mem.get("salvar_foto", True),
                      cfg_mem.get("max_fotos", 5000))
    usar_webapp = bool(cfg["webapp"].get("ativado", True))
    publicador = (Publicador(url, cfg["webapp"].get("enviar_foto", "so_com_animal"),
                             caminho("pendentes")) if usar_webapp else None)
    dispositivo = cfg.get("dispositivo", "pi-1")
    # bicho parado na frente da câmera gera várias fotos seguidas em "aguardando" (cooldown):
    # registra no máximo 1 dessas por animal a cada N s, pra não lotar a memória
    intervalo_aguardando = cfg_mem.get("intervalo_aguardando_s", 10)
    ultimo_aguardando = {}
    acao_dashboard = None
    ultimo_manual = None

    def sincronizar_dashboard(forcar=False):
        if not publicador:
            return
        no = getattr(canal, "nos", {}).get("torre1", {})
        publicador.atuadores = {
            "serial": cfg.get("canal_esp32", {}).get("tipo") == "serial",
            "esp_online": bool(no.get("online") and "torre1" in getattr(canal, "abertas", {})),
            "habilitado": no.get("status", {}).get("modo") == "servos",
            "acao": acao_dashboard,
        }
        publicador.heartbeat(forcar=forcar)

    def enviar_movimento(evento, origem, animal=None, confianca=None):
        nonlocal acao_dashboard
        acao_dashboard = {"id": evento.id, "origem": origem, "animal": animal,
                          "confianca": confianca, "status": "enviado",
                          "servos": [a["params"].get("servo") for a in evento.acoes
                                     if a["acao"] == "servo"]}
        canal.enviar(evento)
        sincronizar_dashboard(forcar=True)

    log.info("pronto | modelo=%s | fonte=%s | canal=%s | webapp=%s", nome_modelo,
             cfg.get("fonte", {}).get("tipo"), cfg.get("canal_esp32", {}).get("tipo"), url)

    def tratar(msg):
        """O que fazer com cada mensagem que veio do ESP32."""
        if msg.tipo == "sensor":
            log.info("ESP32 %s: sensor %s -> pedindo foto", msg.no, msg.dados)
            fonte.pedir_foto(gatilho="pir")
        elif msg.tipo == "ack":
            if acao_dashboard and msg.dados.get("evento") == acao_dashboard["id"]:
                acao_dashboard["status"] = msg.dados.get("status")
                acao_dashboard["erro"] = msg.dados.get("erro")
                sincronizar_dashboard(forcar=True)
            memoria.registrar_esp32(msg)                 # recebido / executado / erro / sem_resposta
            if publicador:
                publicador.atualizar_evento(msg.dados.get("evento"),
                                            msg.dados.get("status", "?"), msg.dados)
        elif msg.tipo in ("status", "capacidades", "offline"):
            memoria.registrar_esp32(msg)

    try:
        while True:
            sincronizar_dashboard()
            # 1. o que o ESP32 disse?
            while (msg := canal.receber()):
                tratar(msg)

            if (acao_dashboard and acao_dashboard["status"] in ("enviado", "recebido")
                    and not getattr(canal, "pendentes", {})):
                acao_dashboard.update(status="erro", erro="ESP não confirmou o fim do movimento")
                sincronizar_dashboard(forcar=True)

            # Em bancada, concluir a série física antes de reconhecer e acionar novamente.
            if cfg.get("aguardar_atuadores") and getattr(canal, "pendentes", {}):
                time.sleep(0.02)
                continue

            if publicador and publicador.comando_servo:
                comando = publicador.comando_servo
                publicador.comando_servo = None
                if comando["id"] != ultimo_manual:
                    alvo = comando["servo"]
                    acoes = [copy.deepcopy(a) for a in decisor.respostas.get("movimento_servos", [])
                             if alvo == "ambos" or str(a["params"].get("servo")) == alvo]
                    if acoes:
                        ultimo_manual = comando["id"]
                        evento = EventoESP32(id=ultimo_manual, animal="teste_manual", confianca=1,
                                             resposta="teste_manual", acoes=acoes)
                        publicador.registrar_evento(evento)
                        enviar_movimento(evento, "manual")
                continue

            # 2. tem foto nova?
            img = fonte.proxima()
            if img is None:
                if publicador:
                    publicador.reenviar_pendentes()
                if getattr(fonte, "terminou", False):
                    log.info("fonte terminou (todas as fotos processadas)")
                    # espera até 5 s pelas últimas confirmações do ESP32
                    fim = time.time() + 5
                    while getattr(canal, "pendentes", None) and time.time() < fim:
                        msg = canal.receber()
                        if msg:
                            tratar(msg)
                        time.sleep(0.02)
                    while (msg := canal.receber()):
                        tratar(msg)
                    break
                time.sleep(0.05)
                continue

            # 3-6. detectar -> decidir -> enviar -> publicar
            t0 = time.perf_counter()
            if publicador and publicador.threshold is not None:
                detector.confianca_min = min(publicador.threshold, decisor.menor_corte)
            deteccoes = detector.detectar(img.imagem)
            t_det = (time.perf_counter() - t0) * 1000

            resultado = ResultadoAnalise(dispositivo=dispositivo, modelo=nome_modelo,
                                         imagem=img.info, deteccoes=[], decisao="nada")
            # em teste de pasta cada foto é independente: sem cooldown
            sincronizar_dashboard(forcar=True)
            if publicador and publicador.comando_servo:
                continue  # Priorizar o teste solicitado durante a inferência.
            decisao = decisor.decidir(deteccoes, resultado.id,
                                      ignorar_cooldown=bool(img.info.lote),
                                      threshold=publicador.threshold if publicador else None)
            resultado.deteccoes = decisao.deteccoes_validas
            resultado.decisao = decisao.decisao
            resultado.animal = decisao.animal
            resultado.confianca = decisao.confianca
            resultado.resposta = decisao.resposta
            resultado.evento = decisao.evento

            # viu animal? -> é um EVENTO
            if decisao.evento:
                enviar_movimento(decisao.evento, "animal", decisao.animal, decisao.confianca)
            resultado.tempo_ms = {"deteccao": round(t_det),
                                  "total": round((time.perf_counter() - t0) * 1000)}
            eh_evento = decisao.animal is not None
            eh_teste = bool(img.info.lote)
            if eh_evento and not eh_teste and decisao.decisao == "aguardando":
                agora = time.monotonic()
                if agora - ultimo_aguardando.get(decisao.animal, -1e9) < intervalo_aguardando:
                    eh_evento = False                     # repetido: não registra
                else:
                    ultimo_aguardando[decisao.animal] = agora
            anotada = (desenhar(img.imagem, resultado.deteccoes)
                       if eh_evento or eh_teste else None)
            if eh_evento and not eh_teste:
                memoria.guardar(resultado, anotada)             # -> memória própria do Pi
            if publicador and (eh_evento or eh_teste):
                publicador.publicar(resultado, anotada)         # -> dashboard (opcional)

            resumo = ", ".join(f"{d.classe} {d.confianca:.0%}" for d in decisao.deteccoes_validas)
            log.info("%-22s %-13s %-8s %-10s %4d ms | %s",
                     (img.info.arquivo or img.info.id)[:22], decisao.decisao,
                     decisao.animal or "-", decisao.resposta or "-", t_det, resumo or "-")
    except KeyboardInterrupt:
        log.info("desligando")
    finally:
        fonte.fechar()
        canal.fechar()


if __name__ == "__main__":
    sys.exit(main())
