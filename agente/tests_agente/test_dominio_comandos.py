import unittest

from robot_agente.dominio import comandos

INICIO = 1_000_000_000_000


class Interpretar(unittest.TestCase):
    def test_aceita_so_o_comando_exato(self):
        self.assertEqual(comandos.interpretar('{"versao": 1, "acao": "shutdown"}'), "shutdown")

    def test_recusa_tudo_que_nao_e_da_lista_fixa(self):
        ruins = [
            None, 42, b'{"versao": 1, "acao": "shutdown"}', "", "shutdown", "nao e json", "[]", '"shutdown"',
            '{"acao": "shutdown"}',
            '{"versao": 2, "acao": "shutdown"}',
            '{"versao": "1", "acao": "shutdown"}',
            '{"versao": true, "acao": "shutdown"}',
            '{"versao": 1, "acao": "reboot"}',
            '{"versao": 1, "acao": "Shutdown"}',
            '{"versao": 1, "acao": "shutdown /r"}',
            '{"versao": 1, "acao": ["shutdown"]}',
            '{"versao": 1, "acao": "shutdown", "comando": "calc.exe"}',
            '{"versao": 1, "acao": "shutdown", "x": "' + "a" * 300 + '"}',
        ]
        for ruim in ruins:
            with self.subTest(ruim=ruim):
                self.assertIsNone(comandos.interpretar(ruim))

    def test_a_lista_e_fixa(self):
        self.assertEqual(comandos.ACOES, frozenset({"shutdown"}))


class Validade(unittest.TestCase):
    def test_comando_recente_enviado_depois_do_inicio_vale(self):
        self.assertTrue(comandos.esta_valida(INICIO + 1_000, INICIO + 2_000, INICIO))
        self.assertTrue(comandos.esta_valida(INICIO, INICIO + 60_000, INICIO))

    def test_comando_enviado_antes_de_o_agente_subir_nao_vale(self):
        self.assertFalse(comandos.esta_valida(INICIO - 1, INICIO + 500, INICIO))

    def test_comando_velho_nao_vale(self):
        self.assertFalse(comandos.esta_valida(INICIO, INICIO + 60_001, INICIO))

    def test_sem_horario_de_envio_nao_vale(self):
        for ruim in (None, "1000000000000", 1.5, True):
            with self.subTest(ruim=ruim):
                self.assertFalse(comandos.esta_valida(ruim, INICIO, 0))


if __name__ == "__main__":
    unittest.main()
