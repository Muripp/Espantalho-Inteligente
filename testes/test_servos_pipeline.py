import unittest

from compartilhado.mensagens import Deteccao
from processador.decisor import Decisor
from processador.canal_esp32.transporte import codificar, mensagem_evento


class ServosPipelineTest(unittest.TestCase):
    def setUp(self):
        self.decisor = Decisor('processador/respostas_servos.yaml')
        self.ave = Deteccao('ave', .9, (0, 0, 10, 10))

    def test_reconhecimentos_sucessivos_geram_tres_ciclos_nos_dois_servos(self):
        for i in range(2):
            resultado = self.decisor.decidir([self.ave], str(i), threshold=.7)
            self.assertEqual(resultado.decisao, 'espantou')
            self.assertEqual(len(resultado.evento.acoes), 2)
            for acao in resultado.evento.acoes:
                self.assertEqual(acao['acao'], 'servo')
                self.assertEqual(acao['params']['repeticoes'], 3)
                self.assertEqual(acao['params']['duracao_ms'], 400)
                self.assertEqual({acao['params']['angulo'], acao['params']['angulo_alternado']}, {70, 110})
            self.assertLessEqual(len(codificar(mensagem_evento(resultado.evento, 'torre1'))), 1024)

    def test_abaixo_do_threshold_nao_aciona(self):
        self.assertIsNone(self.decisor.decidir([self.ave], 'teste', threshold=.95).evento)

    def test_pessoa_reconhecida_bloqueia_servos(self):
        pessoa = Deteccao('pessoa', .95, (0, 0, 10, 10))
        resultado = self.decisor.decidir([self.ave, pessoa], 'teste', threshold=.7)
        self.assertEqual(resultado.decisao, 'pessoa_perto')
        self.assertIsNone(resultado.evento)
