"""Testa as regras de arquitetura e o próprio verificador: quebra a regra de propósito e exige falha."""
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import verificar  # noqa: E402


class Dependencias(unittest.TestCase):
    def test_dominio_real_esta_limpo(self):
        self.assertEqual(verificar.checar_dependencias(verificar.DOMINIO), [])

    def test_o_verificador_reprova_import_proibido(self):
        for linha in (
            "import boto3",
            "import urllib.request",
            "from os import environ",
            "from ..adaptadores import lwa",
            "from robot_lambda.adaptadores.lwa import ClienteLwa",
            "import subprocess",
        ):
            with self.subTest(linha=linha), tempfile.TemporaryDirectory() as pasta:
                (Path(pasta) / "ruim.py").write_text(linha + "\n", encoding="utf-8")
                self.assertTrue(verificar.checar_dependencias(Path(pasta)), linha)

    def test_o_verificador_aceita_import_permitido(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "bom.py").write_text("import re\nfrom typing import Any\n", encoding="utf-8")
            self.assertEqual(verificar.checar_dependencias(Path(pasta)), [])


class Agente(unittest.TestCase):
    def _achados(self, conteudo: str, nome: str = "ruim.py") -> list[str]:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / nome
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(conteudo + "\n", encoding="utf-8")
            return verificar.checar_agente(Path(pasta))

    def test_agente_real_esta_limpo(self):
        self.assertTrue(verificar.AGENTE.exists())
        self.assertEqual(verificar.checar_agente(verificar.AGENTE), [])
        self.assertEqual(verificar.checar_dependencias(verificar.DOMINIO_AGENTE), [])

    def test_o_verificador_reprova_execucao_fora_do_executor(self):
        for linha in (
            "import subprocess",
            "from subprocess import run",
            "import os\nos.system('x')",
            "import os\nos.popen('x')",
            "import os\nos.startfile('x')",
            "eval('1')",
            "exec('x = 1')",
            "__import__('subprocess')",
            "import os\nos.spawnve(0, 'x', [], {})",
            "import os\nos.execvpe('x', [], {})",
            "from os import system as s\ns('x')",
            "import ctypes",
            "from ctypes import wintypes",
            "import boto3",
            "import requests",
            "f = print\nf(**{'shell': True})",
        ):
            with self.subTest(linha=linha):
                self.assertTrue(self._achados(linha), linha)

    def test_o_verificador_reprova_shell_ate_no_executor(self):
        for linha in (
            "import subprocess\nsubprocess.run('x', shell=True)",
            "import subprocess\nligado = True\nsubprocess.run('x', shell=ligado)",
        ):
            with self.subTest(linha=linha):
                self.assertTrue(self._achados(linha, verificar.EXECUTOR_DO_AGENTE), linha)

    def test_ctypes_so_no_leitor_de_credenciais(self):
        self.assertEqual(self._achados("import ctypes", verificar.ARQUIVO_COM_CTYPES), [])

    def test_as_duas_suites_de_teste_existem_e_estao_na_lista(self):
        pastas = [pasta for pasta, _ in verificar.SUITES]
        self.assertEqual(pastas, [verificar.TESTES, verificar.TESTES_AGENTE])
        for pasta in pastas:
            self.assertTrue(list(pasta.glob("test_*.py")), pasta)

    def test_contrato_da_fila_entre_a_lambda_e_o_agente(self):
        """As duas cópias da lista fixa precisam bater, e o que a Lambda envia o agente aceita."""
        import importlib.util
        import json

        from robot_lambda.dominio import comandos as da_lambda

        origem = verificar.DOMINIO_AGENTE / "comandos.py"
        spec = importlib.util.spec_from_file_location("comandos_do_agente", origem)
        do_agente = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(do_agente)
        self.assertEqual(da_lambda.ACOES, do_agente.ACOES)
        self.assertEqual(da_lambda.VERSAO, do_agente.VERSAO)
        for acao in da_lambda.ACOES:
            self.assertEqual(do_agente.interpretar(json.dumps(da_lambda.montar(acao))), acao)

    def test_o_verificador_aceita_o_executor_sem_shell(self):
        codigo = "import subprocess\nsubprocess.run(['x'], shell=False)"
        self.assertEqual(self._achados(codigo, verificar.EXECUTOR_DO_AGENTE), [])


class Segredos(unittest.TestCase):
    def _achados(self, conteudo: str) -> list[str]:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "x.py"
            arquivo.write_text(conteudo, encoding="utf-8")
            return verificar.checar_segredos(Path(pasta), [arquivo])

    def test_reprova_dados_sensiveis(self):
        casos = {
            "chave AWS": "k = 'AKIA" + "ABCDEFGHIJKLMNOP'",
            "client id": "c = 'amzn1.application-oa2-client." + "0123456789abcdef0123456789abcdef'",
            "skill": "s = 'amzn1.ask.skill." + "01234567-0123-0123-0123-0123456789ab'",
            "email": "e = 'pessoa@" + "dominio.com'",
            "mac real": "m = '" + "AA-BB-" + "CC-DD-EE-FF'",
            "caminho windows": "p = 'C:" + "\\Users\\alguem'",
            "caminho linux": "p = '/" + "home/alguem/x'",
        }
        for nome, conteudo in casos.items():
            with self.subTest(nome):
                self.assertTrue(self._achados(conteudo), nome)

    def test_aceita_valores_ficticios_e_noreply(self):
        self.assertEqual(self._achados("m = '00-14-22-01-23-45'\ne = '1+nome@users.noreply.github.com'"), [])

    def test_nunca_imprime_o_valor_achado(self):
        achados = self._achados("k = 'AKIA" + "ABCDEFGHIJKLMNOP'")
        self.assertNotIn("ABCDEFGHIJKLMNOP", " ".join(achados))

    def test_repositorio_real_esta_limpo(self):
        self.assertEqual(verificar.checar_segredos(RAIZ), [])


if __name__ == "__main__":
    unittest.main()
