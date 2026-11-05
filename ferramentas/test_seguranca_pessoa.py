"""Verifica apenas a regra do decisor com entradas artificiais, sem hardware.

Não constitui evidência de detecção visual humana.
"""
from pathlib import Path
import unittest

from compartilhado.mensagens import Deteccao
from processador.decisor import Decisor


class SegurancaPessoa(unittest.TestCase):
    def test_pessoa_bloqueia_evento_inclusive_com_animal(self):
        decisor = Decisor(str(Path(__file__).resolve().parents[1] / "processador/respostas.yaml"))
        pessoa = Deteccao("pessoa", .87, (10, 10, 200, 400))
        ave = Deteccao("ave", .95, (220, 30, 280, 90))
        for deteccoes in ([pessoa], [ave, pessoa]):
            with self.subTest(deteccoes=deteccoes):
                decisao = decisor.decidir(deteccoes, "teste-seguranca")
                self.assertEqual(decisao.decisao, "pessoa_perto")
                self.assertIsNone(decisao.evento)
        self.assertEqual(decisor.ultima_acao, {})


if __name__ == "__main__":
    unittest.main()
