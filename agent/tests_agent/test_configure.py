import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_agent import configure
from robot_agent.errors import CredentialError

URL = "https://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos"
FICTIONAL_ID = "AKIDEXAMPLE0123456"  # 18 characters, example format
FICTIONAL_SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"  # AWS documentation example


class Configure(unittest.TestCase):
    def run_configure(self, answers, secret=FICTIONAL_SECRET, write=None):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("builtins.input", side_effect=answers), \
                mock.patch.object(configure.getpass, "getpass", return_value=secret), \
                mock.patch.object(configure.credentials, "write", side_effect=write) as written, \
                mock.patch.object(configure.config, "data_folder", return_value=Path(folder)), \
                mock.patch("builtins.print") as printed:
            code = configure.main()
            file = Path(folder) / configure.config.FILE
            return code, written, printed, file.exists()

    def test_happy_path_writes_the_credential_and_the_url(self):
        code, written, _, exists = self.run_configure([URL, FICTIONAL_ID])
        self.assertEqual(code, 0)
        written.assert_called_once_with(FICTIONAL_ID, FICTIONAL_SECRET)
        self.assertTrue(exists)

    def test_the_secret_never_appears_in_the_output(self):
        _, _, printed, _ = self.run_configure([URL, FICTIONAL_ID])
        output = " ".join(str(c) for c in printed.call_args_list)
        self.assertNotIn(FICTIONAL_SECRET, output)

    def test_a_url_outside_aws_sqs_writes_nothing(self):
        code, written, _, exists = self.run_configure(["https://example.com/queue", FICTIONAL_ID])
        self.assertEqual(code, 2)
        written.assert_not_called()
        self.assertFalse(exists)

    def test_a_key_id_outside_the_format_writes_nothing(self):
        for bad_id in ("", "short", "lowercase1234567890", "AKID EXAMPLE0123456"):
            with self.subTest(bad_id=bad_id):
                code, written, _, exists = self.run_configure([URL, bad_id])
                self.assertEqual(code, 2)
                written.assert_not_called()
                self.assertFalse(exists)

    def test_an_empty_secret_writes_nothing(self):
        code, written, _, exists = self.run_configure([URL, FICTIONAL_ID], secret="   ")
        self.assertEqual(code, 2)
        written.assert_not_called()
        self.assertFalse(exists)

    def test_a_secret_with_a_control_character_writes_nothing(self):
        for bad in ("\x16", "short", "x" * 39 + "\x16"):
            with self.subTest(bad=repr(bad)):
                code, write, _, exists = self.run_configure([URL, FICTIONAL_ID], secret=bad)
                self.assertEqual(code, 2)
                write.assert_not_called()
                self.assertFalse(exists)

    def test_windows_refusing_the_credential_does_not_write_the_url(self):
        code, _, _, exists = self.run_configure([URL, FICTIONAL_ID], write=CredentialError("refused"))
        self.assertEqual(code, 2)
        self.assertFalse(exists)


if __name__ == "__main__":
    unittest.main()
