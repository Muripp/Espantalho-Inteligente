"""
Banco SQLite do webapp. Vault: "03 Webapp/Webapp" (seção Banco).

analises  : uma linha por foto analisada
deteccoes : uma linha por bicho achado numa foto
eventos_esp32 : uma linha por evento mandado pro ESP32 (animal + resposta + ações)
lotes     : uma linha por "Testar pasta"
"""

import json
import sqlite3
import threading
import time
from datetime import datetime

ESQUEMA = """
CREATE TABLE IF NOT EXISTS analises (
    id TEXT PRIMARY KEY, ts INTEGER, recebido_em INTEGER,
    dispositivo TEXT, modelo TEXT,
    imagem_id TEXT, origem TEXT, gatilho TEXT, arquivo TEXT, data_arquivo INTEGER, lote TEXT,
    largura INTEGER, altura INTEGER,
    decisao TEXT, animal TEXT, confianca REAL, resposta TEXT,
    tempo_deteccao INTEGER, tempo_total INTEGER, foto TEXT
);
CREATE INDEX IF NOT EXISTS ix_analises_ts ON analises(ts);
CREATE INDEX IF NOT EXISTS ix_analises_lote ON analises(lote);

CREATE TABLE IF NOT EXISTS deteccoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, analise_id TEXT, classe TEXT, confianca REAL,
    x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER
);
CREATE INDEX IF NOT EXISTS ix_det_analise ON deteccoes(analise_id);

CREATE TABLE IF NOT EXISTS eventos_esp32 (
    id TEXT PRIMARY KEY, analise_id TEXT, ts INTEGER, animal TEXT, confianca REAL,
    resposta TEXT, acoes TEXT, status TEXT, ts_status INTEGER
);
CREATE INDEX IF NOT EXISTS ix_ev_ts ON eventos_esp32(ts);

CREATE TABLE IF NOT EXISTS lotes (
    id TEXT PRIMARY KEY, criado_em INTEGER, nome TEXT, total INTEGER, enviadas INTEGER DEFAULT 0
);
"""


class Banco:
    def __init__(self, caminho):
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.trava = threading.Lock()
        with self.trava:
            self.con.executescript(ESQUEMA)

    def _q(self, sql, args=()):
        with self.trava:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def _x(self, sql, args=()):
        with self.trava:
            self.con.execute(sql, args)
            self.con.commit()

    # ---------- escrita ----------
    def salvar_analise(self, d: dict, foto: str | None):
        img = d["imagem"]
        with self.trava:
            c = self.con
            c.execute(
                """INSERT OR REPLACE INTO analises VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d["id"], d["ts"], int(time.time() * 1000), d["dispositivo"], d["modelo"],
                 img["id"], img["origem"], img["gatilho"], img.get("arquivo"),
                 img.get("data_arquivo"), img.get("lote"), img.get("largura"), img.get("altura"),
                 d["decisao"], d.get("animal"), d.get("confianca"), d.get("resposta"),
                 d.get("tempo_ms", {}).get("deteccao"), d.get("tempo_ms", {}).get("total"), foto))
            c.execute("DELETE FROM deteccoes WHERE analise_id=?", (d["id"],))
            c.executemany(
                "INSERT INTO deteccoes (analise_id, classe, confianca, x1, y1, x2, y2) "
                "VALUES (?,?,?,?,?,?,?)",
                [(d["id"], x["classe"], x["confianca"], *x["caixa"]) for x in d["deteccoes"]])
            if d.get("evento"):
                self._inserir_evento(c, d["evento"], "enviado")
            c.commit()

    @staticmethod
    def _inserir_evento(con, ev: dict, status: str):
        # INSERT OR IGNORE: o evento pode chegar pelo ESP32 virtual antes da análise
        con.execute(
            "INSERT OR IGNORE INTO eventos_esp32 VALUES (?,?,?,?,?,?,?,?,?)",
            (ev["id"], ev.get("analise_id"), ev["ts"], ev["animal"], ev.get("confianca"),
             ev.get("resposta"), json.dumps(ev.get("acoes", []), ensure_ascii=False),
             status, int(time.time() * 1000)))

    def registrar_evento_recebido(self, ev: dict, status="recebido"):
        """Registra um evento manual ou recebido pelo ESP32 virtual."""
        with self.trava:
            self._inserir_evento(self.con, ev, status)
            self.con.commit()

    def status_evento(self, id_ev: str, status: str):
        self._x("UPDATE eventos_esp32 SET status=?, ts_status=? WHERE id=?",
                (status, int(time.time() * 1000), id_ev))

    def criar_lote(self, id_lote, nome, total):
        self._x("INSERT INTO lotes (id, criado_em, nome, total) VALUES (?,?,?,?)",
                (id_lote, int(time.time() * 1000), nome, total))

    def lote_enviou(self, id_lote):
        self._x("UPDATE lotes SET enviadas = enviadas + 1 WHERE id=?", (id_lote,))

    def apagar_tudo(self):
        with self.trava:
            for t in ("analises", "deteccoes", "eventos_esp32", "lotes"):
                self.con.execute(f"DELETE FROM {t}")
            self.con.commit()

    # ---------- leitura ----------
    def analises(self, lote=None, animal=None, desde=None, limite=50):
        sql, args = "SELECT * FROM analises WHERE 1=1", []
        if lote:
            sql += " AND lote=?"; args.append(lote)
        if animal:
            sql += " AND animal=?"; args.append(animal)
        if desde:
            sql += " AND ts>=?"; args.append(desde)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(limite)
        linhas = self._q(sql, args)
        if linhas:
            ids = [l["id"] for l in linhas]
            marcas = ",".join("?" * len(ids))
            dets = self._q(f"SELECT * FROM deteccoes WHERE analise_id IN ({marcas}) "
                           "ORDER BY confianca DESC", ids)
            evs = self._q(f"SELECT * FROM eventos_esp32 WHERE analise_id IN ({marcas})", ids)
            por = {i: {"deteccoes": [], "evento": None} for i in ids}
            for x in dets:
                por[x["analise_id"]]["deteccoes"].append(
                    {"classe": x["classe"], "confianca": x["confianca"],
                     "caixa": [x["x1"], x["y1"], x["x2"], x["y2"]]})
            for x in evs:
                x["acoes"] = json.loads(x["acoes"] or "[]")
                por[x["analise_id"]]["evento"] = x
            for l in linhas:
                l.update(por[l["id"]])
        return linhas

    def eventos_esp32(self, limite=20):
        linhas = self._q("SELECT * FROM eventos_esp32 ORDER BY ts DESC LIMIT ?", (limite,))
        for l in linhas:
            l["acoes"] = json.loads(l["acoes"] or "[]")
        return linhas

    def lote(self, id_lote):
        l = self._q("SELECT * FROM lotes WHERE id=?", (id_lote,))
        if not l:
            return None
        l = l[0]
        l["processadas"] = self._q("SELECT COUNT(*) n FROM analises WHERE lote=?",
                                   (id_lote,))[0]["n"]
        l["por_animal"] = {r["animal"] or "nada": r["n"] for r in self._q(
            "SELECT animal, COUNT(*) n FROM analises WHERE lote=? GROUP BY animal", (id_lote,))}
        l["por_decisao"] = {r["decisao"]: r["n"] for r in self._q(
            "SELECT decisao, COUNT(*) n FROM analises WHERE lote=? GROUP BY decisao", (id_lote,))}
        t = self._q("SELECT AVG(tempo_deteccao) m FROM analises WHERE lote=?", (id_lote,))[0]
        l["tempo_medio_ms"] = round(t["m"]) if t["m"] else None
        return l

    def lotes(self, limite=10):
        return self._q("SELECT * FROM lotes ORDER BY criado_em DESC LIMIT ?", (limite,))

    def resumo(self, desde_ms: int | None):
        filtro, args = ("WHERE ts>=?", [desde_ms]) if desde_ms else ("", [])
        tot = self._q(f"SELECT COUNT(*) n, MAX(ts) ultimo FROM analises {filtro}", args)[0]
        por_animal = {r["animal"]: r["n"] for r in self._q(
            f"SELECT animal, COUNT(*) n FROM analises {filtro} "
            f"{'AND' if filtro else 'WHERE'} animal IS NOT NULL GROUP BY animal", args)}
        por_decisao = {r["decisao"]: r["n"] for r in self._q(
            f"SELECT decisao, COUNT(*) n FROM analises {filtro} GROUP BY decisao", args)}
        pessoas = self._q(
            "SELECT COUNT(DISTINCT d.analise_id) n FROM deteccoes d JOIN analises a "
            f"ON a.id=d.analise_id WHERE d.classe='pessoa' {'AND a.ts>=?' if desde_ms else ''}",
            args)[0]["n"]
        por_animal["pessoa"] = pessoas
        # por hora (hora local), só análises com animal
        horas = {}
        for r in self._q(f"SELECT ts, animal FROM analises {filtro} "
                         f"{'AND' if filtro else 'WHERE'} animal IS NOT NULL", args):
            h = datetime.fromtimestamp(r["ts"] / 1000).strftime("%Y-%m-%d %H:00")
            horas.setdefault(h, {}).setdefault(r["animal"], 0)
            horas[h][r["animal"]] += 1
        return {"total": tot["n"], "ultimo_ts": tot["ultimo"], "por_animal": por_animal,
                "por_decisao": por_decisao, "por_hora": horas}
