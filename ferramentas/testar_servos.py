"""Teste real de dois SG90: sinais nos GPIO25/26, alimentação externa, GND comum.

Executar: .venv/bin/python -m ferramentas.testar_servos
Cada servo recebe um movimento curto, volta a 90 graus e fica sem PWM.
ACK confirma o processamento do firmware; o movimento deve ser observado na bancada.
"""
import argparse
import json
from pathlib import Path
import time
import uuid

import serial

from compartilhado.mensagens import agora_ms
from processador.canal_esp32.transporte import codificar, decodificar


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--porta', default='/dev/ttyUSB0')
    ap.add_argument('--servo', type=int, choices=(1, 2), help='Sem esta opção, testa os dois em sequência')
    ap.add_argument('--repeticoes', type=int, choices=range(1, 6), default=1)
    args = ap.parse_args()
    pasta = Path('testes/pi')
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / time.strftime('servos-%Y%m%d-%H%M%S.jsonl')
    with serial.Serial(args.porta, 115200, timeout=.2, exclusive=True) as s, caminho.open('x') as log:
        buffer = bytearray()
        def enviar(msg):
            s.write(codificar(msg))
            log.write(json.dumps({'tx': msg}) + '\n'); log.flush()

        def receber(aceita, segundos=5):
            fim = time.monotonic() + segundos
            while time.monotonic() < fim:
                buffer.extend(s.read(s.in_waiting or 1))
                while b'\n' in buffer:
                    fim_linha = buffer.index(b'\n') + 1
                    linha = bytes(buffer[:fim_linha]).decode('utf-8', 'replace')
                    del buffer[:fim_linha]
                    log.write(json.dumps({'rx': linha}) + '\n'); log.flush()
                    msg = decodificar(linha)
                    if msg and aceita(msg):
                        return msg
                if len(buffer) > 8192:
                    raise RuntimeError('Serial sem fim de linha: resposta inválida')
            raise RuntimeError(f'Sem confirmação do ESP. Consulte {caminho}')

        # Não enviar movimento até identificar o firmware e os pinos esperados.
        time.sleep(2)
        enviar({'tipo': 'consulta', 'v': 1})
        caps = receber(lambda m: m.get('tipo') == 'capacidades')['dados']
        if (caps.get('firmware') != 'vigia-servos-1.2.0' or
                caps.get('modo') != 'servos' or caps.get('pinos_servo') != [25, 26] or
                caps.get('atuadores_habilitados') is not True):
            raise RuntimeError(f'Firmware incompatível; nenhum movimento enviado: {caps}')
        enviar({'tipo': 'hora', 'v': 1, 'ts': agora_ms()})
        receber(lambda m: m.get('tipo') == 'status' and m.get('dados', {}).get('relogio_sincronizado'))
        for servo in ([args.servo] if args.servo else [1, 2]):
            id_evento = 'ev-servo-' + uuid.uuid4().hex[:12]
            angulo = 70 if servo == 1 else 110
            evento = {'tipo': 'evento', 'v': 1, 'id': id_evento, 'ts': agora_ms(),
                      'validade_ms': 2000, 'animal': 'ave', 'confianca': 1.0,
                      'resposta': 'teste-bancada', 'acoes': [{'esp32': 'torre1', 'acao': 'servo',
                      'params': {'servo': servo, 'angulo': angulo, 'duracao_ms': 600}}]}
            if args.repeticoes > 1:
                evento['acoes'][0]['params'].update(repeticoes=args.repeticoes,
                    angulo_alternado=110 if servo == 1 else 70, duracao_ms=400)
            print(f'Série de {args.repeticoes} movimento(s).', flush=True)
            print(f'Servo {servo} / GPIO{25 if servo == 1 else 26}: {angulo}° → 90° → PWM desligado', flush=True)
            enviar(evento)
            for esperado in ('recebido', 'executado'):
                msg = receber(lambda m: m.get('tipo') == 'ack' and m.get('dados', {}).get('evento') == id_evento, segundos=8)
                dados = msg['dados']
                if dados.get('status') != esperado or dados.get('simulado') is not False:
                    raise RuntimeError(f'ACK inesperado: {msg}')
                print(f'  ESP confirmou: {esperado}', flush=True)
            time.sleep(.5)
        print(f'Teste concluído no firmware. Confirme visualmente os movimentos. Log: {caminho}')


if __name__ == '__main__':
    main()
