"""
Decisor: olha as detecções e decide se age, com qual resposta, e gera os comandos pro ESP32.
Vault: "02 Processador (Raspberry Pi)/Decisor" e "04 ESP32/Respostas por animal".

Ordem:
  1. filtra detecções abaixo do corte de confiança DO ANIMAL
  2. tem pessoa?                     -> "pessoa_perto" (não age)
  3. sobrou animal?                  -> não: "nada"
  4. pega o animal mais confiante
  5. agiu nesse animal há pouco?     -> "aguardando" (cooldown)
  6. busca a regra do animal (ou "padrao") e sorteia uma resposta pelos pesos
  7. monta UM EventoESP32 (animal + resposta + ações)  -> "espantou"

Ainda NÃO faz (anotado no vault): confirmar em 2 de 3 fotos, escalada,
horário de silêncio, medir se o bicho foi embora.
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import yaml

from compartilhado.mensagens import Deteccao, EventoESP32

log = logging.getLogger("decisor")


@dataclass
class Decisao:
    decisao: str                      # "espantou" | "pessoa_perto" | "aguardando" | "nada"
    animal: Optional[str] = None
    confianca: Optional[float] = None
    resposta: Optional[str] = None
    evento: Optional[EventoESP32] = None      # só quando decisao == "espantou"
    deteccoes_validas: list = field(default_factory=list)


class Decisor:
    def __init__(self, caminho_respostas: str):
        with open(caminho_respostas, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.respostas = cfg.get("respostas", {})
        self.regras = cfg.get("regras", {})
        self.padroes = cfg.get("padroes", {})
        self.ultima_acao = {}            # animal -> time.monotonic() da última ação
        self._validar()

    # ---------- configuração ----------
    def _validar(self):
        for nome, passos in self.respostas.items():
            for p in passos:
                if "esp32" not in p or "acao" not in p:
                    raise ValueError(f"respostas.yaml: resposta '{nome}' tem passo sem "
                                     f"'esp32' ou 'acao': {p}")
        for animal, regra in self.regras.items():
            for nome in (regra.get("respostas") or {}):
                if nome not in self.respostas:
                    raise ValueError(f"respostas.yaml: regra '{animal}' usa resposta "
                                     f"'{nome}', que não existe")

    def regra(self, classe: str) -> dict:
        return self.regras.get(classe, self.regras.get("padrao", {}))

    def corte(self, classe: str) -> float:
        return self.regra(classe).get("confianca_min", self.padroes.get("confianca_min", 0.45))

    @property
    def menor_corte(self) -> float:
        """O detector precisa usar o menor corte de todos (os outros a gente filtra aqui)."""
        cortes = [r.get("confianca_min") for r in self.regras.values() if "confianca_min" in r]
        return min(cortes + [self.padroes.get("confianca_min", 0.45)])

    # ---------- decisão ----------
    def decidir(self, deteccoes: list, analise_id: str, ignorar_cooldown=False) -> Decisao:
        validas = [d for d in deteccoes if d.confianca >= self.corte(d.classe)]

        if any(self.regra(d.classe).get("bloqueia_tudo") for d in validas):
            animais = [d for d in validas if not self.regra(d.classe).get("bloqueia_tudo")]
            principal = max(animais, key=lambda d: d.confianca, default=None)
            return Decisao("pessoa_perto",
                           animal=principal.classe if principal else None,
                           confianca=principal.confianca if principal else None,
                           deteccoes_validas=validas)

        if not validas:
            return Decisao("nada", deteccoes_validas=validas)

        principal: Deteccao = max(validas, key=lambda d: d.confianca)
        animal = principal.classe
        regra = self.regra(animal)

        agora = time.monotonic()
        cooldown = regra.get("cooldown_s", 30)
        if not ignorar_cooldown and agora - self.ultima_acao.get(animal, -1e9) < cooldown:
            return Decisao("aguardando", animal, principal.confianca,
                           deteccoes_validas=validas)

        pesos = regra.get("respostas") or {}
        if not pesos:
            log.warning("animal '%s' não tem resposta configurada", animal)
            return Decisao("nada", animal, principal.confianca, deteccoes_validas=validas)
        nome = random.choices(list(pesos), weights=list(pesos.values()))[0]

        evento = EventoESP32(
            animal=animal, confianca=principal.confianca, resposta=nome,
            acoes=[{"esp32": p["esp32"], "acao": p["acao"], "params": dict(p.get("params", {}))}
                   for p in self.respostas[nome]],
            validade_ms=self.padroes.get("validade_ms", 2000), analise_id=analise_id,
        )
        if not ignorar_cooldown:
            self.ultima_acao[animal] = agora
        return Decisao("espantou", animal, principal.confianca, nome, evento, validas)
