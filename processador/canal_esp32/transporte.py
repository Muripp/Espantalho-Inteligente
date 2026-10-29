"""
Base dos canais REAIS com o ESP32 (serial e MQTT).

Aqui fica tudo que é igual nos dois transportes:
  - como uma mensagem vira texto (JSON em UMA linha) e volta
  - entrega confiável: espera o ack, reenvia, desiste e avisa
  - saber se cada ESP32 está vivo (mensagens "status")

Os transportes (serial_uart.py, mqtt.py) só precisam implementar 2 coisas:
  _mandar(esp32, mensagem: dict) -> bool        coloca a mensagem no fio
  _pegar() -> (esp32, mensagem: dict) | None     tira uma mensagem do fio, sem travar

Protocolo completo (com exemplos e diagramas): vault "04 ESP32/Protocolo ESP32 ↔ Pi".
"""

import json
import logging
import time
from abc import abstractmethod
from typing import Optional

from compartilhado.mensagens import VERSAO, EventoESP32, MensagemESP32, agora_ms, novo_id

from .base import CanalESP32

log = logging.getLogger("canal")

TAMANHO_MAX = 1024            # bytes por mensagem (o ESP32 tem pouca memória)


# ---------------------------------------------------------------- codificação
def codificar(msg: dict) -> bytes:
    """dict -> b'{"tipo":"evento",...}\\n'  (JSON compacto numa linha só, UTF-8)."""
    linha = json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n"
    dados = linha.encode("utf-8")
    if len(dados) > TAMANHO_MAX:
        raise ValueError(f"mensagem com {len(dados)} bytes (máximo {TAMANHO_MAX})")
    return dados


def decodificar(linha: str) -> Optional[dict]:
    """Uma linha recebida -> dict. Linhas que não são JSON (ex.: prints de debug
    do ESP32) são ignoradas e devolvem None."""
    linha = linha.strip()
    if not linha.startswith("{"):
        if linha:
            log.debug("ignorando linha que não é JSON: %r", linha[:80])
        return None
    try:
        msg = json.loads(linha)
    except json.JSONDecodeError:
        log.warning("JSON inválido do ESP32: %r", linha[:120])
        return None
    return msg if isinstance(msg, dict) and "tipo" in msg else None


def mensagem_evento(evento: EventoESP32, esp32: str) -> dict:
    """O que vai pelo fio pra UM ESP32: o evento, só com as ações DELE."""
    d = evento.to_dict()
    d["tipo"] = "evento"
    d["acoes"] = [a for a in evento.acoes if a.get("esp32") == esp32]
    d.pop("analise_id", None)          # o ESP32 não precisa disso (economiza bytes)
    return d


def mensagem_hora() -> dict:
    """Acerta o relógio do ESP32 (ele não tem relógio próprio)."""
    return {"tipo": "hora", "v": VERSAO, "ts": agora_ms()}


# ---------------------------------------------------------------- canal base
class CanalTransporte(CanalESP32):
    """Entrega confiável por cima de um transporte qualquer."""

    def __init__(self, espera_ack_s: float = 1.0, max_reenvios: int = 2,
                 sem_status_s: float = 90, **_):
        self.espera_ack_s = espera_ack_s
        self.max_reenvios = max_reenvios
        self.sem_status_s = sem_status_s
        self.pendentes = {}         # (id_evento, esp32) -> {...}
        self.saida = []             # mensagens já prontas pra receber() devolver
        self.nos = {}               # esp32 -> {"visto": ts, "online": bool, "status": {...}}

    # ---- o que cada transporte implementa
    @abstractmethod
    def _mandar(self, esp32: str, msg: dict) -> bool: ...

    @abstractmethod
    def _pegar(self) -> Optional[tuple]: ...

    # ---- Pi -> ESP32
    def enviar(self, evento: EventoESP32) -> bool:
        destinos = sorted({a["esp32"] for a in evento.acoes})
        tudo_ok = True
        for esp32 in destinos:
            msg = mensagem_evento(evento, esp32)
            ok = self._mandar(esp32, msg)
            tudo_ok &= ok
            agora = time.monotonic()
            self.pendentes[(evento.id, esp32)] = {
                "msg": msg, "estado": "aguardando", "tentativas": 1, "enviado": agora,
                "proxima": agora + self.espera_ack_s,
                "limite": agora + evento.validade_ms / 1000,
            }
            log.info("-> %s evento %s: %s -> %s (%d ações)%s", esp32, evento.id, evento.animal,
                     evento.resposta, len(msg["acoes"]), "" if ok else "  [FALHOU, vou tentar de novo]")
        return tudo_ok

    # ---- ESP32 -> Pi
    def receber(self) -> Optional[MensagemESP32]:
        # 1. lê tudo que chegou no fio
        while True:
            item = self._pegar()
            if item is None:
                break
            esp32, msg = item
            m = self._tratar(esp32, msg)
            if m:
                self.saida.append(m)
        # 2. reenvios / desistências
        self._verificar_pendentes()
        # 3. quem sumiu?
        self._verificar_nos()
        return self.saida.pop(0) if self.saida else None

    def _tratar(self, esp32: str, msg: dict) -> Optional[MensagemESP32]:
        no = msg.get("no") or esp32
        tipo = msg.get("tipo")
        dados = msg.get("dados") or {}
        info = self.nos.setdefault(no, {"visto": 0, "online": False, "status": {}})
        if tipo == "offline":                       # MQTT: "testamento" publicado pelo broker
            if info["online"]:
                log.warning("ESP32 %s ficou offline", no)
            info["online"] = False
            return MensagemESP32(no=no, tipo="offline", dados={})
        info["visto"] = time.monotonic()
        if not info["online"]:
            info["online"] = True
            log.info("ESP32 %s online", no)
            self._mandar(no, mensagem_hora())

        if tipo == "ack":
            chave = (dados.get("evento"), no)
            status = dados.get("status")
            p = self.pendentes.get(chave)
            if p and status in ("recebido", "executado", "erro"):
                dados.setdefault("latencia_ms", round((time.monotonic() - p["enviado"]) * 1000))
                if status == "recebido":
                    p["estado"] = "recebido"          # chegou: para de reenviar, espera o fim
                else:
                    self.pendentes.pop(chave)         # terminou (bem ou mal)
            log.info("<- %s ack %s: %s%s", no, dados.get("evento"), status,
                     f" ({dados.get('erro')})" if dados.get("erro") else "")
        elif tipo == "status":
            info["status"] = dados
            log.debug("<- %s status %s", no, dados)
        elif tipo == "sensor":
            log.info("<- %s sensor %s", no, dados)
        elif tipo == "capacidades":
            log.info("<- %s capacidades %s", no, dados)
        else:
            log.debug("<- %s tipo desconhecido %r", no, tipo)

        return MensagemESP32(no=no, tipo=tipo, dados=dados,
                             id=msg.get("id") or novo_id("m"), ts=msg.get("ts") or agora_ms())

    def _verificar_pendentes(self):
        agora = time.monotonic()
        for chave, p in list(self.pendentes.items()):
            id_ev, esp32 = chave
            if p["estado"] == "recebido":
                # o ESP32 recebeu; se nunca disser "executado", esquece depois de 15 s
                if agora - p["enviado"] > 15:
                    self.pendentes.pop(chave)
                continue
            if agora < p["proxima"]:
                continue
            if p["tentativas"] <= self.max_reenvios and agora < p["limite"]:
                p["tentativas"] += 1
                p["proxima"] = agora + self.espera_ack_s
                log.warning("sem ack de %s pro evento %s: reenviando (tentativa %d)",
                            esp32, id_ev, p["tentativas"])
                self._mandar(esp32, p["msg"])
            else:
                self.pendentes.pop(chave)
                log.error("ESP32 %s não respondeu o evento %s (%d tentativas): desisti",
                          esp32, id_ev, p["tentativas"])
                self.saida.append(MensagemESP32(no=esp32, tipo="ack", dados={
                    "evento": id_ev, "status": "sem_resposta", "tentativas": p["tentativas"]}))

    def _verificar_nos(self):
        agora = time.monotonic()
        for no, info in self.nos.items():
            if info["online"] and agora - info["visto"] > self.sem_status_s:
                info["online"] = False
                log.warning("ESP32 %s sumiu (nenhuma mensagem há %d s)", no, self.sem_status_s)
