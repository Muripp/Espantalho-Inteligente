import unittest
from concurrent.futures import ThreadPoolExecutor

from webapp.atuadores import ControleServos


class DashboardServosTest(unittest.TestCase):
    def setUp(self):
        self.agora = 0
        self.controle = ControleServos(lambda: self.agora)
        self.pronto = {'serial': True, 'esp_online': True, 'habilitado': True, 'acao': None}

    def test_offline_nao_enfileira_teste(self):
        with self.assertRaises(ConnectionError):
            self.controle.solicitar('ambos')

    def test_comando_redeliverado_ate_processador_confirmar(self):
        self.controle.atualizar(self.pronto)
        pedido = self.controle.solicitar('1')
        with self.assertRaises(BlockingIOError):
            self.controle.solicitar('2')
        primeiro = self.controle.atualizar(self.pronto)
        self.assertEqual(primeiro['id'], pedido['id'])
        self.assertEqual(self.controle.atualizar(self.pronto), primeiro)
        ativo = {**self.pronto, 'acao': {'id': pedido['id'], 'origem': 'manual', 'status': 'recebido'}}
        self.assertIsNone(self.controle.atualizar(ativo))
        self.assertTrue(self.controle.estado()['ativo'])
        self.assertFalse(self.controle.estado()['disponivel'])
        self.controle.atualizar({**ativo, 'acao': {**ativo['acao'], 'status': 'executado'}})
        self.assertTrue(self.controle.estado()['disponivel'])

    def test_reacao_de_animal_e_erro_sao_expostos(self):
        acao = {'id': 'ev-1', 'origem': 'animal', 'animal': 'ave', 'confianca': .91, 'status': 'recebido'}
        self.controle.atualizar({**self.pronto, 'acao': acao})
        self.assertEqual(self.controle.estado()['acao'], acao)
        with self.assertRaises(BlockingIOError):
            self.controle.solicitar('ambos')
        self.controle.atualizar({**self.pronto, 'acao': {**acao, 'status': 'erro'}})
        self.assertFalse(self.controle.estado()['ativo'])
        self.assertTrue(self.controle.estado()['disponivel'])

    def test_perda_de_heartbeat_desabilita_botoes(self):
        self.controle.atualizar(self.pronto)
        self.agora = 16
        self.assertFalse(self.controle.estado()['online'])
        self.assertFalse(self.controle.estado()['disponivel'])

    def test_teste_expirado_nao_e_executado_mais_tarde(self):
        self.controle.atualizar(self.pronto)
        self.controle.solicitar('ambos')
        self.agora = 11
        self.assertIsNone(self.controle.atualizar(self.pronto))
        self.assertEqual(self.controle.estado()['acao']['status'], 'erro')

    def test_cliques_concorrentes_geram_apenas_um_teste(self):
        self.controle.atualizar(self.pronto)
        def solicitar(_):
            try:
                self.controle.solicitar('ambos')
                return True
            except BlockingIOError:
                return False
        with ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(sum(executor.map(solicitar, range(8))), 1)


if __name__ == '__main__':
    unittest.main()
