"""Estado de bancada e fila de um teste manual, consumida pelo processador."""
import copy
import threading
import time

from compartilhado.mensagens import novo_id


class ControleServos:
    def __init__(self, relogio=time.monotonic):
        self.relogio = relogio
        self.trava = threading.Lock()
        self.contato = -1e9
        self.snapshot = {}
        self.comando = None
        self.ultimo_erro = None

    def _estado(self):
        online = (self.relogio() - self.contato < 15 and
                  self.snapshot.get('serial') and self.snapshot.get('esp_online') and
                  self.snapshot.get('habilitado'))
        acao = self.snapshot.get('acao')
        if self.comando and self.relogio() - self.comando['criado'] > 10:
            self.ultimo_erro = {'id': self.comando['id'], 'origem': 'manual',
                                'status': 'erro', 'erro': 'Teste expirou antes de ser enviado'}
            self.comando = None
        if self.ultimo_erro:
            acao = self.ultimo_erro
        ativo = bool(online and acao and acao.get('status') in ('enviado', 'recebido'))
        return {'online': bool(online), 'ativo': ativo, 'acao': acao,
                'teste_pendente': bool(self.comando),
                'disponivel': bool(online and not ativo and not self.comando)}

    def estado(self):
        with self.trava:
            return copy.deepcopy(self._estado())

    def atualizar(self, snapshot):
        with self.trava:
            self.contato = self.relogio()
            self.snapshot = copy.deepcopy(snapshot)
            acao = snapshot.get('acao') or {}
            if acao.get('status') in ('enviado', 'recebido'):
                self.ultimo_erro = None
            if self.comando and acao.get('id') == self.comando['id']:
                self.comando = None
                self.ultimo_erro = None
            self._estado()
            if self.comando and not self._estado()['ativo']:
                return {k: v for k, v in self.comando.items() if k != 'criado'}
            return None

    def solicitar(self, servo):
        with self.trava:
            estado = self._estado()
            if not estado['online']:
                raise ConnectionError('ESP ou processador sem conexão para o teste')
            if not estado['disponivel']:
                raise BlockingIOError('Aguarde o movimento atual terminar')
            self.ultimo_erro = None
            self.comando = {'id': novo_id('ev-manual'), 'servo': servo,
                            'criado': self.relogio()}
            return {'id': self.comando['id'], 'ok': True}
