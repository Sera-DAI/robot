"""Tests the architecture rules and the verifier itself: breaks a rule on purpose and demands a failure."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import verify  # noqa: E402


class Dependencies(unittest.TestCase):
    def test_real_domain_is_clean(self):
        self.assertEqual(verify.check_dependencies(verify.DOMAIN), [])

    def test_the_verifier_rejects_a_forbidden_import(self):
        for line in (
            "import boto3",
            "import urllib.request",
            "from os import environ",
            "from ..adapters import lwa",
            "from robot_lambda.adapters.lwa import LwaClient",
            "import subprocess",
        ):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / "bad.py").write_text(line + "\n", encoding="utf-8")
                self.assertTrue(verify.check_dependencies(Path(folder)), line)

    def test_the_verifier_accepts_an_allowed_import(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "good.py").write_text("import re\nfrom typing import Any\n", encoding="utf-8")
            self.assertEqual(verify.check_dependencies(Path(folder)), [])


class Agent(unittest.TestCase):
    def _findings(self, content: str, name: str = "bad.py") -> list[str]:
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content + "\n", encoding="utf-8")
            return verify.check_agent(Path(folder))

    def test_real_agent_is_clean(self):
        self.assertTrue(verify.AGENT.exists())
        self.assertEqual(verify.check_agent(verify.AGENT), [])
        self.assertEqual(verify.check_dependencies(verify.AGENT_DOMAIN), [])

    def test_the_verifier_rejects_execution_outside_the_executor(self):
        for line in (
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
            with self.subTest(line=line):
                self.assertTrue(self._findings(line), line)

    def test_the_verifier_rejects_shell_even_in_the_executor(self):
        for line in (
            "import subprocess\nsubprocess.run('x', shell=True)",
            "import subprocess\nenabled = True\nsubprocess.run('x', shell=enabled)",
        ):
            with self.subTest(line=line):
                self.assertTrue(self._findings(line, verify.AGENT_EXECUTOR), line)

    def test_ctypes_only_in_the_credentials_reader(self):
        self.assertEqual(self._findings("import ctypes", verify.CTYPES_FILE), [])

    def test_both_test_suites_exist_and_are_listed(self):
        folders = [folder for folder, _ in verify.SUITES]
        self.assertEqual(folders, [verify.TESTS, verify.AGENT_TESTS])
        for folder in folders:
            self.assertTrue(list(folder.glob("test_*.py")), folder)

    def test_queue_contract_between_the_lambda_and_the_agent(self):
        """The two copies of the fixed list must match, and what the Lambda sends the agent accepts."""
        import importlib.util
        import json

        from robot_lambda.domain import commands as from_lambda

        source = verify.AGENT_DOMAIN / "commands.py"
        spec = importlib.util.spec_from_file_location("agent_commands", source)
        from_agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(from_agent)
        self.assertEqual(from_lambda.ACTIONS, from_agent.ACTIONS)
        self.assertEqual(from_lambda.VERSION, from_agent.VERSION)
        for action in from_lambda.ACTIONS:
            self.assertEqual(from_agent.interpret(json.dumps(from_lambda.build(action))), action)

    def test_the_verifier_accepts_the_executor_without_shell(self):
        code = "import subprocess\nsubprocess.run(['x'], shell=False)"
        self.assertEqual(self._findings(code, verify.AGENT_EXECUTOR), [])


class Secrets(unittest.TestCase):
    def _findings(self, content: str) -> list[str]:
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "x.py"
            file.write_text(content, encoding="utf-8")
            return verify.check_secrets(Path(folder), [file])

    def test_rejects_sensitive_data(self):
        cases = {
            "AWS key": "k = 'AKIA" + "ABCDEFGHIJKLMNOP'",
            "client id": "c = 'amzn1.application-oa2-client." + "0123456789abcdef0123456789abcdef'",
            "skill": "s = 'amzn1.ask.skill." + "01234567-0123-0123-0123-0123456789ab'",
            "email": "e = 'person@" + "mail.test'",
            "real mac": "m = '" + "AA-BB-" + "CC-DD-EE-FF'",
            "windows path": "p = 'C:" + "\\Users\\someone'",
            "linux path": "p = '/" + "home/someone/x'",
        }
        for name, content in cases.items():
            with self.subTest(name):
                self.assertTrue(self._findings(content), name)

    def test_accepts_fictional_values_and_noreply(self):
        self.assertEqual(self._findings("m = '00-14-22-01-23-45'\ne = '1+someone@users.noreply.github.com'"), [])

    def test_never_prints_the_value_found(self):
        findings = self._findings("k = 'AKIA" + "ABCDEFGHIJKLMNOP'")
        self.assertNotIn("ABCDEFGHIJKLMNOP", " ".join(findings))

    def test_real_repository_is_clean(self):
        self.assertEqual(verify.check_secrets(ROOT), [])


if __name__ == "__main__":
    unittest.main()
