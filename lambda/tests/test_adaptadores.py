import io
import json
import unittest
import urllib.error
from decimal import Decimal
from unittest import mock

from robot_lambda.adaptadores import fila, gateway, invocador, lwa, tokens
from robot_lambda.erros import ArmazenamentoErro, FilaErro, GatewayErro, InvocacaoErro, LwaErro

SEGREDO = "segredo-do-cliente-de-teste"
CODIGO = "codigo-de-teste"


class RespostaFalsa(io.BytesIO):
    def __init__(self, corpo=b"{}", status=200):
        super().__init__(corpo)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_erro(status, corpo=b'{"detalhe": "contem segredo-do-cliente-de-teste"}'):
    return urllib.error.HTTPError("https://exemplo.invalido", status, "x", {}, io.BytesIO(corpo))


class Lwa(unittest.TestCase):
    def setUp(self):
        self.cliente = lwa.ClienteLwa("id-do-cliente-de-teste", SEGREDO)

    def test_troca_de_codigo_monta_o_pedido_e_normaliza_a_resposta(self):
        resposta = RespostaFalsa(json.dumps({"access_token": "a", "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"}).encode())
        with mock.patch("urllib.request.urlopen", return_value=resposta) as urlopen:
            dados = self.cliente.trocar_codigo(CODIGO)
        pedido = urlopen.call_args.args[0]
        self.assertEqual(pedido.full_url, lwa.URL_TOKEN)
        self.assertEqual(pedido.get_method(), "POST")
        corpo = pedido.data.decode()
        for esperado in ("grant_type=authorization_code", f"code={CODIGO}", "client_id=", "client_secret="):
            self.assertIn(esperado, corpo)
        self.assertEqual(dados, {"access_token": "a", "refresh_token": "r", "expires_in": 3600})

    def test_renovacao_usa_refresh_token(self):
        resposta = RespostaFalsa(json.dumps({"access_token": "a", "refresh_token": "r", "expires_in": 3600}).encode())
        with mock.patch("urllib.request.urlopen", return_value=resposta) as urlopen:
            self.cliente.renovar("refresh-x")
        corpo = urlopen.call_args.args[0].data.decode()
        self.assertIn("grant_type=refresh_token", corpo)
        self.assertIn("refresh_token=refresh-x", corpo)

    def test_erro_http_nao_vaza_corpo_nem_segredo(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_erro(400)):
            with self.assertRaises(LwaErro) as ctx:
                self.cliente.trocar_codigo(CODIGO)
        self.assertIn("400", str(ctx.exception))
        for proibido in (SEGREDO, CODIGO, "detalhe"):
            self.assertNotIn(proibido, str(ctx.exception))

    def test_falha_de_rede_e_resposta_incompleta(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(LwaErro):
                self.cliente.renovar("r")
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b'{"access_token": "a"}')):
            with self.assertRaises(LwaErro):
                self.cliente.renovar("r")
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"nao-e-json")):
            with self.assertRaises(LwaErro):
                self.cliente.renovar("r")


class Gateway(unittest.TestCase):
    def test_envia_json_por_post(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"", 202)) as urlopen:
            gateway.ClienteGateway().enviar({"event": {"x": 1}})
        pedido = urlopen.call_args.args[0]
        self.assertEqual(pedido.full_url, gateway.URL_GATEWAY)
        self.assertEqual(pedido.get_method(), "POST")
        self.assertEqual(json.loads(pedido.data), {"event": {"x": 1}})

    def test_erros_nao_vazam_corpo(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_erro(403)):
            with self.assertRaises(GatewayErro) as ctx:
                gateway.ClienteGateway().enviar({"event": {"token": "token-de-teste"}})
        self.assertIn("403", str(ctx.exception))
        self.assertNotIn("token-de-teste", str(ctx.exception))
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(GatewayErro):
                gateway.ClienteGateway().enviar({})


class TabelaFalsa:
    def __init__(self, item=None, falha=False):
        self.item, self.falha, self.gravado = item, falha, None

    def get_item(self, Key):
        if self.falha:
            raise RuntimeError("detalhe interno com token-de-teste")
        return {"Item": self.item} if self.item else {}

    def put_item(self, Item):
        if self.falha:
            raise RuntimeError("detalhe interno com token-de-teste")
        self.gravado = Item


class RecursoFalso:
    def __init__(self, tabela):
        self.tabela = tabela

    def Table(self, nome):
        return self.tabela


class Tokens(unittest.TestCase):
    def test_ida_e_volta(self):
        tabela = TabelaFalsa()
        repo = tokens.TokensDynamo("t", RecursoFalso(tabela))
        repo.salvar({"access_token": "a", "refresh_token": "r", "expira_em": 10})
        self.assertEqual(tabela.gravado, {"id": "dono", "access_token": "a", "refresh_token": "r", "expira_em": 10})
        tabela.item = tabela.gravado
        self.assertEqual(repo.obter(), {"access_token": "a", "refresh_token": "r", "expira_em": 10})

    def test_le_numero_decimal_do_dynamodb_como_int(self):
        item = {"id": "dono", "access_token": "a", "refresh_token": "r", "expira_em": Decimal("123")}
        lido = tokens.TokensDynamo("t", RecursoFalso(TabelaFalsa(item))).obter()
        self.assertEqual(lido["expira_em"], 123)
        self.assertIsInstance(lido["expira_em"], int)

    def test_item_incompleto_vira_erro_do_projeto(self):
        item = {"id": "dono", "access_token": "a", "expira_em": Decimal("1")}
        with self.assertRaises(ArmazenamentoErro):
            tokens.TokensDynamo("t", RecursoFalso(TabelaFalsa(item))).obter()

    def test_vazio_devolve_none(self):
        self.assertIsNone(tokens.TokensDynamo("t", RecursoFalso(TabelaFalsa())).obter())

    def test_erro_do_banco_nao_vaza_detalhe(self):
        repo = tokens.TokensDynamo("t", RecursoFalso(TabelaFalsa(falha=True)))
        for chamada in (repo.obter, lambda: repo.salvar({"access_token": "a", "refresh_token": "r", "expira_em": 1})):
            with self.assertRaises(ArmazenamentoErro) as ctx:
                chamada()
            self.assertNotIn("token-de-teste", str(ctx.exception))


class Invocador(unittest.TestCase):
    def test_invocacao_assincrona(self):
        cliente = mock.Mock()
        invocador.InvocadorLambda("funcao", cliente).disparar({"a": 1})
        argumentos = cliente.invoke.call_args.kwargs
        self.assertEqual(argumentos["InvocationType"], "Event")
        self.assertEqual(argumentos["FunctionName"], "funcao")
        self.assertEqual(json.loads(argumentos["Payload"]), {"a": 1})

    def test_falha_vira_erro_do_projeto(self):
        cliente = mock.Mock()
        cliente.invoke.side_effect = RuntimeError("detalhe")
        with self.assertRaises(InvocacaoErro):
            invocador.InvocadorLambda("funcao", cliente).disparar({})


class Fila(unittest.TestCase):
    def test_envia_o_comando_como_json_para_a_url_configurada(self):
        cliente = mock.Mock()
        fila.FilaSqs("https://fila.invalido/teste", cliente).enviar({"versao": 1, "acao": "shutdown"})
        chamada = cliente.send_message.call_args.kwargs
        self.assertEqual(chamada["QueueUrl"], "https://fila.invalido/teste")
        self.assertEqual(json.loads(chamada["MessageBody"]), {"versao": 1, "acao": "shutdown"})

    def test_falha_do_sdk_vira_erro_sem_detalhe(self):
        cliente = mock.Mock()
        cliente.send_message.side_effect = RuntimeError("contem " + SEGREDO)
        with self.assertRaises(FilaErro) as erro:
            fila.FilaSqs("https://fila.invalido/teste", cliente).enviar({"acao": "shutdown"})
        self.assertNotIn(SEGREDO, str(erro.exception))
        self.assertIsNone(erro.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
