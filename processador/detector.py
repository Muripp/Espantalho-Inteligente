"""
Detector de animais usando um modelo YOLO exportado em ONNX.

Roda só com onnxruntime + OpenCV + numpy (sem PyTorch), então instala fácil
em Raspberry Pi, notebook ou PC. Funciona tanto com o modelo pré-treinado
(yolo11n.onnx, 80 classes do COCO) quanto com o espantalho_aves.onnx
(9 classes): os nomes das classes são lidos
direto de dentro do arquivo .onnx.
"""

import ast

import cv2
import numpy as np
import onnxruntime as ort

from compartilhado.mensagens import Deteccao


class Detector:
    def __init__(self, caminho_modelo, confianca_min=0.4, iou_nms=0.5, tamanho=None,
                 nms_ignora_classe=True):
        self.nms_ignora_classe = nms_ignora_classe
        opcoes = ort.SessionOptions()
        opcoes.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sessao = ort.InferenceSession(
            caminho_modelo, opcoes, providers=["CPUExecutionProvider"]
        )
        self.nome_entrada = self.sessao.get_inputs()[0].name
        meta = self.sessao.get_modelmeta().custom_metadata_map

        # Nomes das classes gravados pelo Ultralytics na exportação
        self.classes = ast.literal_eval(meta["names"]) if "names" in meta else {}

        # Tamanho de entrada: o do modelo, a menos que seja passado outro
        if tamanho is None:
            tamanho = ast.literal_eval(meta.get("imgsz", "[640, 640]"))[0]
        self.tamanho = int(tamanho)
        self.confianca_min = confianca_min
        self.iou_nms = iou_nms

    def _letterbox(self, img):
        """Redimensiona mantendo a proporção e completa com bordas cinza."""
        h, w = img.shape[:2]
        escala = self.tamanho / max(h, w)
        nh, nw = round(h * escala), round(w * escala)
        redim = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        topo = (self.tamanho - nh) // 2
        esq = (self.tamanho - nw) // 2
        tela = np.full((self.tamanho, self.tamanho, 3), 114, dtype=np.uint8)
        tela[topo:topo + nh, esq:esq + nw] = redim
        return tela, escala, esq, topo

    def detectar(self, img_bgr):
        """Recebe uma imagem BGR (OpenCV) e devolve uma lista de Deteccao."""
        tela, escala, dx, dy = self._letterbox(img_bgr)
        blob = cv2.cvtColor(tela, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)
        blob = np.ascontiguousarray(blob[None], dtype=np.float32) / 255.0

        saida = self.sessao.run(None, {self.nome_entrada: blob})[0][0]  # (4+nc, N)
        saida = saida.T                                                 # (N, 4+nc)
        pontuacoes = saida[:, 4:]
        ids = pontuacoes.argmax(axis=1)
        confs = pontuacoes[np.arange(len(ids)), ids]
        manter = confs >= self.confianca_min
        if not manter.any():
            return []

        caixas_cxcywh = saida[manter, :4]
        ids, confs = ids[manter], confs[manter]

        # cx,cy,w,h (no espaço do letterbox) -> x,y,w,h na imagem original
        cx, cy, bw, bh = caixas_cxcywh.T
        x1 = (cx - bw / 2 - dx) / escala
        y1 = (cy - bh / 2 - dy) / escala
        bw, bh = bw / escala, bh / escala
        caixas_xywh = np.stack([x1, y1, bw, bh], axis=1)

        # Supressão de não-máximos (evita caixas duplicadas). Por padrão ignora a
        # classe: se o mesmo bicho sair como "outro_animal 80%" e "porco 50%",
        # fica só a caixa mais confiante.
        h, w = img_bgr.shape[:2]
        resultado = []
        grupos_nms = [None] if self.nms_ignora_classe else np.unique(ids)
        for c in grupos_nms:
            sel = np.arange(len(ids)) if c is None else np.where(ids == c)[0]
            idx = cv2.dnn.NMSBoxes(
                caixas_xywh[sel].tolist(), confs[sel].tolist(),
                self.confianca_min, self.iou_nms,
            )
            for i in np.array(idx).flatten():
                k = sel[i]
                x, y, bw_, bh_ = caixas_xywh[k]
                caixa = (
                    int(max(0, x)), int(max(0, y)),
                    int(min(w, x + bw_)), int(min(h, y + bh_)),
                )
                resultado.append(Deteccao(
                    classe=self.classes.get(int(ids[k]), str(int(ids[k]))),
                    confianca=float(confs[k]),
                    caixa=caixa,
                ))
        resultado.sort(key=lambda d: d.confianca, reverse=True)
        return resultado
