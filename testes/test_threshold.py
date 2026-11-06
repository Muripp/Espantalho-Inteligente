import unittest

from compartilhado.mensagens import Deteccao
from processador.decisor import Decisor


class ThresholdTest(unittest.TestCase):
    def setUp(self):
        self.decisor = Decisor('processador/respostas.yaml')

    def detectar(self, valor):
        return Deteccao(classe='ave', confianca=valor, caixa=(0, 0, 20, 20))

    def test_abaixo_nao_registra_nem_dispara_cooldown(self):
        resultado = self.decisor.decidir([self.detectar(0.699)], 'teste', threshold=0.7)
        self.assertEqual(resultado.decisao, 'nada')
        self.assertIsNone(resultado.animal)
        self.assertIsNone(resultado.evento)
        self.assertEqual(resultado.deteccoes_validas, [])
        self.assertEqual(self.decisor.ultima_acao, {})

    def test_igual_ao_corte_e_aceito(self):
        resultado = self.decisor.decidir([self.detectar(0.7)], 'teste', threshold=0.7)
        self.assertEqual(resultado.decisao, 'espantou')

    def test_reduzir_threshold_substitui_corte_da_classe(self):
        resultado = self.decisor.decidir([self.detectar(0.2)], 'teste', threshold=0.2)
        self.assertEqual(resultado.decisao, 'espantou')

    def test_sem_dashboard_preserva_regras(self):
        resultado = self.decisor.decidir([self.detectar(0.34)], 'teste')
        self.assertEqual(resultado.decisao, 'nada')


if __name__ == '__main__':
    unittest.main()
