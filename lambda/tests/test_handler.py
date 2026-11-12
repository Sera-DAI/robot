import os
import unittest
from unittest import mock

from robot_lambda import handler

AMBIENTE = {
    "ROBOT_MAC": "00-14-22-01-23-45",
    "TABELA_TOKENS": "tabela-de-teste",
    "LWA_CLIENT_ID": "id-de-teste",
    "LWA_CLIENT_SECRET": "segredo-de-teste",
    "AWS_LAMBDA_FUNCTION_NAME": "funcao-de-teste",
    "FILA_URL": "https://fila.invalido/teste",
}


_MONTAR_REAL = handler._montar


class Handler(unittest.TestCase):
    def setUp(self):
        handler._deps = None
        self.addCleanup(setattr, handler, "_deps", None)

    def _montar_sem_sdk(self):
        with mock.patch.dict(os.environ, AMBIENTE, clear=True), \
                mock.patch.object(handler, "TokensDynamo"), \
                mock.patch.object(handler, "InvocadorLambda"), \
                mock.patch.object(handler, "FilaSqs"):
            return _MONTAR_REAL()

    def test_monta_as_dependencias_a_partir_do_ambiente(self):
        deps = self._montar_sem_sdk()
        self.assertEqual(deps.config.mac, AMBIENTE["ROBOT_MAC"])
        self.assertEqual(deps.config.endpoint_id, "pc-principal")
        self.assertRegex(deps.agora_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.00Z$")
        self.assertNotEqual(deps.novo_id(), deps.novo_id())

    def test_variavel_obrigatoria_ausente_falha_alto(self):
        for faltando in AMBIENTE:
            with self.subTest(faltando=faltando):
                ambiente = {k: v for k, v in AMBIENTE.items() if k != faltando}
                with mock.patch.dict(os.environ, ambiente, clear=True), \
                        mock.patch.object(handler, "TokensDynamo"), \
                        mock.patch.object(handler, "InvocadorLambda"), \
                        mock.patch.object(handler, "FilaSqs"):
                    with self.assertRaises(KeyError):
                        handler._montar()

    def test_lidar_cacheia_as_dependencias_e_responde_ao_discovery(self):
        evento = {
            "directive": {
                "header": {"namespace": "Alexa.Discovery", "name": "Discover", "payloadVersion": "3", "messageId": "m"},
                "payload": {"scope": {"type": "BearerToken", "token": "token-de-teste"}},
            }
        }
        with mock.patch.object(handler, "_montar", side_effect=lambda: self._montar_sem_sdk()) as montar:
            r1 = handler.lidar(evento, None)
            handler.lidar(evento, None)
        self.assertEqual(montar.call_count, 1)
        self.assertEqual(r1["event"]["header"]["name"], "Discover.Response")


if __name__ == "__main__":
    unittest.main()
