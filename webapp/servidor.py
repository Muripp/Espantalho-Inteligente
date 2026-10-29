"""
Webapp do VIGIA: recebe o que o processador viu, guarda e mostra no dashboard.
Também faz o papel de simulador (fila de fotos + ESP32 virtual).
Vault: "03 Webapp/Webapp".

Rodar (de dentro da pasta vigia/):
    python -m uvicorn webapp.servidor:app --port 8000
e abrir http://localhost:8000
"""

import base64
import csv
import io
import os
import threading
import time
from collections import deque
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from compartilhado.mensagens import MensagemESP32, agora_ms, novo_id

from .banco import Banco

PASTA = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(PASTA, "dados")
FOTOS = os.path.join(DADOS, "fotos")
os.makedirs(FOTOS, exist_ok=True)

app = FastAPI(title="VIGIA")
banco = Banco(os.path.join(DADOS, "vigia.db"))

# Filas em memória (zeram se reiniciar o servidor; ok pra simulador)
fila_imagens: deque = deque()          # fotos esperando o processador
fila_esp32: deque = deque()            # mensagens "do ESP32" esperando o processador
trava = threading.Lock()
estado = {"ultimo_contato_processador": 0}


def ms(): return int(time.time() * 1000)


# ======================= usado pelo PROCESSADOR =======================

@app.post("/api/analises")
async def receber_analise(request: Request):
    d = await request.json()
    foto = None
    if d.get("foto_jpeg_b64"):
        foto = f"{d['id']}.jpg"
        with open(os.path.join(FOTOS, foto), "wb") as f:
            f.write(base64.b64decode(d["foto_jpeg_b64"]))
    banco.salvar_analise(d, foto)
    estado["ultimo_contato_processador"] = ms()
    return {"ok": True}


@app.get("/api/simulador/proxima-imagem")
def proxima_imagem():
    estado["ultimo_contato_processador"] = ms()
    with trava:
        if not fila_imagens:
            return Response(status_code=204)
        return fila_imagens.popleft()


@app.post("/api/esp32-virtual/eventos")
async def esp32_recebe_evento(request: Request):
    """O "ESP32 virtual" recebe um evento (animal + ações) e responde um ack automático."""
    ev = await request.json()
    banco.registrar_evento_recebido(ev)
    no = ev["acoes"][0]["esp32"] if ev.get("acoes") else "esp32"
    ack = MensagemESP32(no=no, tipo="ack",
                        dados={"evento": ev["id"], "status": "executado", "latencia_ms": 5})
    with trava:
        fila_esp32.append(ack.to_dict())
    return {"ok": True}


@app.get("/api/esp32-virtual/mensagens")
def esp32_mensagens():
    with trava:
        if not fila_esp32:
            return Response(status_code=204)
        return fila_esp32.popleft()


@app.post("/api/eventos-esp32/{id_ev}/status")
async def status_evento(id_ev: str, request: Request):
    d = await request.json()
    banco.status_evento(id_ev, d.get("status", "?"))
    return {"ok": True}


# ======================= usado pelo DASHBOARD =======================

@app.get("/api/status")
def status():
    ultimo = estado["ultimo_contato_processador"]
    with trava:
        na_fila = len(fila_imagens)
    return {"agora": ms(), "processador_online": ms() - ultimo < 5000,
            "ultimo_contato_processador": ultimo or None, "fila_imagens": na_fila}


@app.get("/api/resumo")
def resumo(horas: int = 24):
    return banco.resumo(ms() - horas * 3600_000 if horas > 0 else None)


@app.get("/api/analises")
def analises(lote: str | None = None, animal: str | None = None, limite: int = 50):
    return banco.analises(lote=lote, animal=animal, limite=min(limite, 5000))


@app.get("/api/eventos-esp32")
def eventos_esp32(limite: int = 20):
    return banco.eventos_esp32(limite)


# ---------- teste de pasta (lotes) ----------

@app.post("/api/lotes")
async def criar_lote(request: Request):
    d = await request.json()
    id_lote = novo_id("lote")
    banco.criar_lote(id_lote, d.get("nome", "pasta"), int(d.get("total", 0)))
    return {"id": id_lote}


@app.post("/api/simulador/imagem")
async def enviar_imagem(arquivo: UploadFile = File(...), lote: str | None = Form(None),
                        nome: str | None = Form(None), data_arquivo: int | None = Form(None)):
    conteudo = await arquivo.read()
    info = {"id": novo_id("img"), "ts": agora_ms(), "origem": "webapp",
            "gatilho": "teste" if lote else "manual", "arquivo": nome or arquivo.filename,
            "data_arquivo": data_arquivo, "lote": lote}
    with trava:
        fila_imagens.append({"info": info, "imagem_b64": base64.b64encode(conteudo).decode()})
        n = len(fila_imagens)
    if lote:
        banco.lote_enviou(lote)
    return {"ok": True, "id": info["id"], "fila": n}


@app.get("/api/lotes")
def lotes():
    return banco.lotes()


@app.get("/api/lotes/{id_lote}")
def ver_lote(id_lote: str):
    l = banco.lote(id_lote)
    if not l:
        raise HTTPException(404, "lote não existe")
    with trava:
        l["na_fila"] = sum(1 for x in fila_imagens if x["info"]["lote"] == id_lote)
    return l


@app.post("/api/lotes/{id_lote}/cancelar")
def cancelar_lote(id_lote: str):
    with trava:
        antes = len(fila_imagens)
        restantes = [x for x in fila_imagens if x["info"]["lote"] != id_lote]
        fila_imagens.clear()
        fila_imagens.extend(restantes)
    return {"removidas": antes - len(restantes)}


@app.get("/api/lotes/{id_lote}/csv")
def csv_lote(id_lote: str):
    linhas = banco.analises(lote=id_lote, limite=100000)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["arquivo", "data_arquivo", "processado_em", "decisao", "animal", "confianca",
                "resposta", "todas_deteccoes", "acoes_esp32", "tempo_deteccao_ms", "largura",
                "altura", "modelo", "dispositivo", "id_analise"])
    fmt = lambda t: datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d %H:%M:%S") if t else ""
    for a in reversed(linhas):
        w.writerow([a["arquivo"], fmt(a["data_arquivo"]), fmt(a["ts"]), a["decisao"],
                    a["animal"] or "", f"{a['confianca']:.2f}".replace(".", ",") if a["confianca"] else "",
                    a["resposta"] or "",
                    " | ".join(f"{d['classe']} {d['confianca']:.0%}" for d in a["deteccoes"]),
                    " | ".join(f"{x['acao']} {x['params']}" for x in (a["evento"] or {}).get("acoes", [])),
                    a["tempo_deteccao"], a["largura"], a["altura"], a["modelo"],
                    a["dispositivo"], a["id"]])
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{id_lote}.csv"'})


@app.post("/api/limpar")
def limpar():
    """Apaga todas as análises do banco e as fotos (usado pelo botão 'Limpar dados')."""
    banco.apagar_tudo()
    for f in os.listdir(FOTOS):
        os.remove(os.path.join(FOTOS, f))
    with trava:
        fila_imagens.clear()
    return {"ok": True}


# ======================= páginas =======================

app.mount("/fotos", StaticFiles(directory=FOTOS), name="fotos")
app.mount("/static", StaticFiles(directory=os.path.join(PASTA, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(PASTA, "static", "index.html"))
