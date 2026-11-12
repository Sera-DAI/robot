import unittest

from robot_agente import aplicacao
from robot_agente.adaptadores.sqs import Mensagem
from robot_agente.aplicacao import Deps, ciclo, rodar
from robot_agente.erros import DesligamentoErro, FilaErro

INICIO = 1_000_000_000_000
DESLIGAR = '{"versao": 1, "acao": "shutdown"}'


class FilaFalsa:
    def __init__(self, lotes=(), falha_ao_apagar=False):
        self.lotes, self.apagados, self.falha_ao_apagar = list(lotes), [], falha_ao_apagar

    def receber(self):
        if not self.lotes:
            return []
        lote = self.lotes.pop(0)
        if isinstance(lote, Exception):
            raise lote
        return lote

    def apagar(self, recibo):
        if self.falha_ao_apagar:
            raise FilaErro("x")
        self.apagados.append(recibo)


def msg(corpo=DESLIGAR, recibo="r1", enviada=INICIO + 1_000):
    return Mensagem(corpo=corpo, recibo=recibo, enviada_em_ms=enviada)


def montar(fila, executar=None, agora=INICIO + 2_000):
    executadas, sonos = [], []
    deps = Deps(
        fila=fila,
        executar=executar or executadas.append,
        agora_ms=lambda: agora,
        dormir=sonos.append,
    )
    return deps, executadas, sonos


class Ciclo(unittest.TestCase):
    def test_comando_valido_e_apagado_e_executado_uma_vez(self):
        fila = FilaFalsa([[msg()]])
        d, executadas, _ = montar(fila)
        self.assertEqual(ciclo(d, INICIO), 1)
        self.assertEqual(executadas, ["shutdown"])
        self.assertEqual(fila.apagados, ["r1"])

    def test_apaga_antes_de_executar(self):
        ordem = []
        fila = FilaFalsa([[msg()]])
        fila.apagar = lambda recibo: ordem.append("apagar")
        d, _, _ = montar(fila, executar=lambda acao: ordem.append("executar"))
        ciclo(d, INICIO)
        self.assertEqual(ordem, ["apagar", "executar"])

    def test_se_nao_apagar_nao_executa(self):
        d, executadas, _ = montar(FilaFalsa([[msg()]], falha_ao_apagar=True))
        with self.assertLogs(aplicacao.LOG, level="ERROR"):
            self.assertEqual(ciclo(d, INICIO), 0)
        self.assertEqual(executadas, [])

    def test_mensagem_estranha_e_apagada_sem_executar(self):
        fila = FilaFalsa([[msg(corpo='{"versao": 1, "acao": "calc.exe"}'), msg(corpo="lixo", recibo="r2")]])
        d, executadas, _ = montar(fila)
        with self.assertLogs(aplicacao.LOG, level="WARNING") as capturado:
            ciclo(d, INICIO)
        self.assertEqual(executadas, [])
        self.assertEqual(fila.apagados, ["r1", "r2"])
        self.assertNotIn("calc.exe", "\n".join(capturado.output))

    def test_comando_de_antes_do_inicio_ou_sem_horario_e_apagado_sem_executar(self):
        fila = FilaFalsa([[msg(enviada=INICIO - 5_000), msg(recibo="r2", enviada=None)]])
        d, executadas, _ = montar(fila)
        with self.assertLogs(aplicacao.LOG, level="WARNING"):
            ciclo(d, INICIO)
        self.assertEqual(executadas, [])
        self.assertEqual(fila.apagados, ["r1", "r2"])

    def test_comando_velho_e_apagado_sem_executar(self):
        fila = FilaFalsa([[msg(enviada=INICIO + 1_000)]])
        d, executadas, _ = montar(fila, agora=INICIO + 61_001)
        with self.assertLogs(aplicacao.LOG, level="WARNING"):
            ciclo(d, INICIO)
        self.assertEqual(executadas, [])
        self.assertEqual(fila.apagados, ["r1"])

    def test_comando_repetido_no_lote_executa_uma_vez(self):
        fila = FilaFalsa([[msg(), msg(recibo="r2")]])
        d, executadas, _ = montar(fila)
        self.assertEqual(ciclo(d, INICIO), 1)
        self.assertEqual(executadas, ["shutdown"])
        self.assertEqual(fila.apagados, ["r1", "r2"])

    def test_falha_do_windows_nao_derruba_o_agente(self):
        def recusar(acao):
            raise DesligamentoErro("x")

        d, _, _ = montar(FilaFalsa([[msg()]]), executar=recusar)
        with self.assertLogs(aplicacao.LOG, level="ERROR"):
            self.assertEqual(ciclo(d, INICIO), 0)


class Rodar(unittest.TestCase):
    def test_erro_de_fila_espera_com_recuo_e_continua(self):
        fila = FilaFalsa([FilaErro("a"), FilaErro("b"), [msg(enviada=INICIO + 2_000)]])
        d, executadas, sonos = montar(fila)
        voltas = iter([True, True, True, False])
        with self.assertLogs(aplicacao.LOG, level="INFO"):
            rodar(d, continuar=lambda: next(voltas))
        self.assertEqual(sonos, [5, 10])
        self.assertEqual(executadas, ["shutdown"])

    def test_o_recuo_tem_teto(self):
        fila = FilaFalsa([FilaErro("x")] * 10)
        d, _, sonos = montar(fila)
        voltas = iter([True] * 10 + [False])
        with self.assertLogs(aplicacao.LOG, level="INFO"):
            rodar(d, continuar=lambda: next(voltas))
        self.assertEqual(max(sonos), aplicacao.ESPERA_MAXIMA_S)


if __name__ == "__main__":
    unittest.main()
