import unittest

from robot_lambda.dominio import comandos


class Comandos(unittest.TestCase):
    def test_monta_o_desligar(self):
        self.assertEqual(comandos.montar("shutdown"), {"versao": 1, "acao": "shutdown"})

    def test_recusa_acao_fora_da_lista(self):
        for ruim in ("reboot", "", "Shutdown", "shutdown /s", None):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                comandos.montar(ruim)

    def test_a_lista_e_fixa(self):
        self.assertEqual(comandos.ACOES, frozenset({"shutdown"}))


if __name__ == "__main__":
    unittest.main()
