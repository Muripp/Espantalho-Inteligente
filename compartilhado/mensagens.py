"""
Contratos de mensagens do VIGIA.

Tudo que passa de uma parte pra outra (processador <-> webapp <-> ESP32)
usa estas classes. A explicação de cada campo está no vault do Obsidian:
"01 Arquitetura/Contratos de mensagens".

Regra: se mudar o formato de uma mensagem, aumente VERSAO.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

VERSAO = 1


def novo_id(prefixo: str) -> str:
    """Identificador único curto, ex.: 'an-3f9a1c2b'."""
    return f"{prefixo}-{uuid.uuid4().hex[:8]}"


def agora_ms() -> int:
    """Horário atual em milissegundos desde 1970 (UTC)."""
    return int(time.time() * 1000)


@dataclass
class Deteccao:
    classe: str          # ex.: "ave"
    confianca: float     # 0 a 1
    caixa: tuple         # (x1, y1, x2, y2) em pixels da imagem original

    def to_dict(self) -> dict:
        return {"classe": self.classe, "confianca": round(float(self.confianca), 4),
                "caixa": [int(v) for v in self.caixa]}

    @classmethod
    def from_dict(cls, d: dict) -> "Deteccao":
        return cls(d["classe"], float(d["confianca"]), tuple(d["caixa"]))


@dataclass
class ImagemInfo:
    """Metadados de uma imagem (a imagem em si fica em ImagemRecebida.imagem)."""
    id: str
    ts: int                              # quando a foto foi tirada/recebida
    origem: str                          # "pasta" | "webcam" | "webapp" | "picamera"
    gatilho: str                         # "movimento" | "periodico" | "pir" | "manual" | "teste"
    arquivo: Optional[str] = None        # nome do arquivo, se veio de um
    data_arquivo: Optional[int] = None   # data de modificação do arquivo (ms)
    lote: Optional[str] = None           # id do teste de pasta, se fizer parte de um
    largura: int = 0
    altura: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ImagemInfo":
        campos = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in campos})


@dataclass
class ImagemRecebida:
    """Sai da Fonte de imagens e entra no Detector. Não viaja pela rede assim."""
    info: ImagemInfo
    imagem: object       # array BGR do OpenCV


@dataclass
class EventoESP32:
    """Pi -> ESP32: "vi este animal, faça isto". Uma mensagem por evento.

    O ESP32 recebe o animal (pra registrar/mostrar) e a lista de ações já resolvida
    pelo banco de respostas do Pi. Ele só executa as ações cujo `esp32` é ele mesmo.
    """
    animal: str                          # ex.: "ave"
    confianca: float
    resposta: str                        # nome da resposta escolhida (ex.: "predador")
    acoes: list = field(default_factory=list)   # [{"esp32": "torre1", "acao": "som", "params": {...}}]
    validade_ms: int = 2000
    analise_id: Optional[str] = None
    id: str = field(default_factory=lambda: novo_id("ev"))
    ts: int = field(default_factory=agora_ms)
    v: int = VERSAO

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confianca"] = round(float(self.confianca), 4)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EventoESP32":
        campos = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in campos})


@dataclass
class MensagemESP32:
    no: str
    tipo: str                            # "sensor" | "ack" | "status" | "capacidades" | "offline"
    dados: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: novo_id("m"))
    ts: int = field(default_factory=agora_ms)
    v: int = VERSAO

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MensagemESP32":
        campos = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in campos})


@dataclass
class ResultadoAnalise:
    """Processador -> Webapp (POST /api/analises)."""
    dispositivo: str
    modelo: str
    imagem: ImagemInfo
    deteccoes: list                      # list[Deteccao]
    decisao: str                         # "espantou" | "pessoa_perto" | "aguardando" | "nada"
    animal: Optional[str] = None
    confianca: Optional[float] = None    # confiança do animal escolhido
    resposta: Optional[str] = None       # nome da resposta usada (ex.: "predador")
    evento: Optional[EventoESP32] = None # o que foi mandado pro ESP32 (só se "espantou")
    tempo_ms: dict = field(default_factory=dict)   # {"deteccao": 83, "total": 110}
    foto_jpeg_b64: Optional[str] = None  # foto anotada (opcional)
    id: str = field(default_factory=lambda: novo_id("an"))
    ts: int = field(default_factory=agora_ms)
    v: int = VERSAO

    def to_dict(self) -> dict:
        return {
            "v": self.v, "id": self.id, "ts": self.ts,
            "dispositivo": self.dispositivo, "modelo": self.modelo,
            "imagem": self.imagem.to_dict(),
            "deteccoes": [d.to_dict() for d in self.deteccoes],
            "decisao": self.decisao, "animal": self.animal,
            "confianca": None if self.confianca is None else round(float(self.confianca), 4),
            "resposta": self.resposta,
            "evento": self.evento.to_dict() if self.evento else None,
            "tempo_ms": self.tempo_ms,
            "foto_jpeg_b64": self.foto_jpeg_b64,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResultadoAnalise":
        return cls(
            v=d.get("v", VERSAO), id=d["id"], ts=d["ts"],
            dispositivo=d["dispositivo"], modelo=d["modelo"],
            imagem=ImagemInfo.from_dict(d["imagem"]),
            deteccoes=[Deteccao.from_dict(x) for x in d.get("deteccoes", [])],
            decisao=d["decisao"], animal=d.get("animal"), confianca=d.get("confianca"),
            resposta=d.get("resposta"),
            evento=EventoESP32.from_dict(d["evento"]) if d.get("evento") else None,
            tempo_ms=d.get("tempo_ms", {}), foto_jpeg_b64=d.get("foto_jpeg_b64"),
        )
