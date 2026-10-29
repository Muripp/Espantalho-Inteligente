"""
Memória própria do Raspberry Pi: guarda cada evento (animal visto) num arquivo,
independente do webapp e do ESP32.

    memoria/eventos.jsonl          uma linha JSON por evento (fácil de ler, de anexar, de importar)
    memoria/fotos/<id>.jpg         a foto anotada de cada evento (opcional)
    memoria/esp32.jsonl            o que o ESP32 respondeu (acks, status) -> dá pra saber se executou

É a "caixa-preta" do espantalho: mesmo sem rede nenhuma, fica tudo registrado.
Vault: "02 Processador (Raspberry Pi)/Memória local".
"""

import json
import logging
import os

import cv2

from compartilhado.mensagens import ResultadoAnalise

log = logging.getLogger("memoria")


class Memoria:
    def __init__(self, pasta: str, salvar_foto: bool = True, max_fotos: int = 5000):
        self.pasta = pasta
        self.fotos = os.path.join(pasta, "fotos")
        self.arquivo = os.path.join(pasta, "eventos.jsonl")
        self.arquivo_esp32 = os.path.join(pasta, "esp32.jsonl")
        self.salvar_foto = salvar_foto
        self.max_fotos = max_fotos
        os.makedirs(self.fotos, exist_ok=True)

    def guardar(self, resultado: ResultadoAnalise, imagem_anotada=None):
        d = resultado.to_dict()
        d.pop("foto_jpeg_b64", None)
        if self.salvar_foto and imagem_anotada is not None:
            nome = f"{resultado.ts}_{resultado.id}.jpg"   # começa pela data: ordem = cronológica
            cv2.imwrite(os.path.join(self.fotos, nome), imagem_anotada,
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
            d["foto"] = f"fotos/{nome}"
            self._limitar_fotos()
        with open(self.arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def registrar_esp32(self, msg):
        """Guarda o que o ESP32 disse (MensagemESP32): ack, status, capacidades..."""
        with open(self.arquivo_esp32, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")

    def _limitar_fotos(self):
        """Apaga as fotos mais antigas se passar do limite (o cartão SD do Pi é pequeno).
        O registro em eventos.jsonl nunca é apagado."""
        fotos = sorted(os.listdir(self.fotos))
        for nome in fotos[: max(0, len(fotos) - self.max_fotos)]:
            os.remove(os.path.join(self.fotos, nome))
