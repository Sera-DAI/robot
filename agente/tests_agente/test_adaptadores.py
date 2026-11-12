import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from robot_agente import config
from robot_agente.adaptadores import desligamento, sigv4, sqs
from robot_agente.erros import ConfigErro, DesligamentoErro, FilaErro

# Valores de exemplo da documentação da AWS, não são credenciais reais.
ID_EXEMPLO = "AKIDEXAMPLE"
SEGREDO_EXEMPLO = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
URL = "https://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos"
INSTANTE = "20260101T000000Z"


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SigV4(unittest.TestCase):
    def test_chave_de_assinatura_bate_com_o_exemplo_da_documentacao(self):
        chave = sigv4.chave_de_assinatura(SEGREDO_EXEMPLO, "20120215", "us-east-1", "iam")
        self.assertEqual(chave.hex(), "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d")

    def test_assinatura_de_um_pedido_fixo_nao_muda(self):
        # Valor conferido contra o botocore (SigV4Auth) fora do repositório.
        cabecalhos = sigv4.assinar_post(
            host="sqs.us-east-1.amazonaws.com", caminho="/", corpo=b'{"QueueUrl": "x"}',
            cabecalhos={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AmazonSQS.ReceiveMessage"},
            id_chave=ID_EXEMPLO, segredo=SEGREDO_EXEMPLO, regiao="us-east-1", servico="sqs", instante=INSTANTE,
        )
        self.assertEqual(
            cabecalhos["authorization"],
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20260101/us-east-1/sqs/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date;x-amz-target, "
            "Signature=4e84c39671b14c14a14bf11c6e36e7252a38548f09e549ba410d41012ca4b28f",
        )
        self.assertNotIn(SEGREDO_EXEMPLO, json.dumps(cabecalhos))


class Sqs(unittest.TestCase):
    def setUp(self):
        self.cliente = sqs.ClienteSqs(URL, ID_EXEMPLO, SEGREDO_EXEMPLO, agora_amz=lambda: INSTANTE)

    def test_url_da_fila_so_pode_ser_do_sqs_da_aws(self):
        self.assertEqual(sqs.regiao_da_url(URL), "us-east-1")
        ruins = [
            "http://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos",
            "https://sqs.us-east-1.amazonaws.com.exemplo.invalido/000000000000/robot-comandos",
            "https://exemplo.invalido/000000000000/robot-comandos",
            "https://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos?x=1",
            "https://sqs.us-east-1.amazonaws.com/abc/robot-comandos",
            "", None,
        ]
        for ruim in ruins:
            with self.subTest(ruim=ruim), self.assertRaises(FilaErro):
                sqs.regiao_da_url(ruim)

    def test_receber_monta_o_pedido_e_le_as_mensagens(self):
        corpo = json.dumps({"Messages": [
            {"MessageId": "1", "ReceiptHandle": "recibo-1", "Body": '{"versao": 1, "acao": "shutdown"}',
             "Attributes": {"SentTimestamp": "1000000001000"}},
            {"MessageId": "2", "ReceiptHandle": "recibo-2", "Body": "x"},
            {"MessageId": "3"},
        ]}).encode()
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(corpo)) as urlopen:
            mensagens = self.cliente.receber()
        pedido = urlopen.call_args.args[0]
        self.assertEqual(pedido.full_url, "https://sqs.us-east-1.amazonaws.com/")
        self.assertEqual(pedido.get_method(), "POST")
        self.assertEqual(pedido.get_header("X-amz-target"), "AmazonSQS.ReceiveMessage")
        self.assertTrue(pedido.get_header("Authorization").startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/"))
        enviado = json.loads(pedido.data)
        self.assertEqual(enviado["QueueUrl"], URL)
        self.assertEqual(enviado["WaitTimeSeconds"], 20)
        self.assertGreater(urlopen.call_args.kwargs["timeout"], 20)
        self.assertEqual(
            mensagens,
            [
                sqs.Mensagem('{"versao": 1, "acao": "shutdown"}', "recibo-1", 1000000001000),
                sqs.Mensagem("x", "recibo-2", None),
            ],
        )

    def test_fila_vazia_devolve_lista_vazia(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"{}")):
            self.assertEqual(self.cliente.receber(), [])

    def test_apagar_envia_o_recibo(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"")) as urlopen:
            self.cliente.apagar("recibo-1")
        pedido = urlopen.call_args.args[0]
        self.assertEqual(pedido.get_header("X-amz-target"), "AmazonSQS.DeleteMessage")
        self.assertEqual(json.loads(pedido.data), {"QueueUrl": URL, "ReceiptHandle": "recibo-1"})

    def test_erros_nao_vazam_segredo_nem_corpo(self):
        http = urllib.error.HTTPError(URL, 403, "x", {}, io.BytesIO(("contem " + SEGREDO_EXEMPLO).encode()))
        for falha in (http, OSError("contem " + SEGREDO_EXEMPLO)):
            with self.subTest(falha=type(falha).__name__):
                with mock.patch("urllib.request.urlopen", side_effect=falha), self.assertRaises(FilaErro) as erro:
                    self.cliente.receber()
                self.assertNotIn(SEGREDO_EXEMPLO, str(erro.exception))
                self.assertIsNone(erro.exception.__cause__)

    def test_resposta_que_nao_e_json_vira_erro(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"<html>")), self.assertRaises(FilaErro):
            self.cliente.receber()


class Desligamento(unittest.TestCase):
    """O subprocess é sempre substituído: nenhum teste desliga máquina nenhuma."""

    def test_chama_o_shutdown_do_windows_com_argumentos_fixos_e_sem_shell(self):
        with mock.patch.object(desligamento.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            desligamento.executar("shutdown")
        argumentos = run.call_args.args[0]
        self.assertTrue(argumentos[0].lower().endswith("shutdown.exe"))
        self.assertEqual(argumentos[1:4], ["/s", "/t", "30"])
        self.assertIs(run.call_args.kwargs["shell"], False)

    def test_acao_fora_da_lista_nunca_chega_ao_subprocess(self):
        with mock.patch.object(desligamento.subprocess, "run") as run:
            for ruim in ("reboot", "calc.exe", "", "shutdown /r", None):
                with self.subTest(ruim=ruim), self.assertRaises(DesligamentoErro):
                    desligamento.executar(ruim)
        run.assert_not_called()

    def test_recusa_do_windows_vira_erro(self):
        with mock.patch.object(desligamento.subprocess, "run", return_value=mock.Mock(returncode=5)):
            with self.assertRaises(DesligamentoErro):
                desligamento.executar("shutdown")
        with mock.patch.object(desligamento.subprocess, "run", side_effect=OSError("x")):
            with self.assertRaises(DesligamentoErro):
                desligamento.executar("shutdown")


class Config(unittest.TestCase):
    def test_grava_e_le_a_url_da_fila(self):
        with tempfile.TemporaryDirectory() as pasta:
            config.gravar_url_da_fila(URL, Path(pasta) / "dados")
            self.assertEqual(config.ler_url_da_fila(Path(pasta) / "dados"), URL)

    def test_config_ausente_ou_invalida_vira_erro_claro(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ConfigErro):
                config.ler_url_da_fila(Path(pasta))
            for conteudo in ("lixo", "[]", '{"outra": 1}', '{"fila_url": 5}'):
                (Path(pasta) / config.ARQUIVO).write_text(conteudo, encoding="utf-8")
                with self.subTest(conteudo=conteudo), self.assertRaises(ConfigErro):
                    config.ler_url_da_fila(Path(pasta))


if __name__ == "__main__":
    unittest.main()
