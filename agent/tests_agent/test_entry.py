import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_agent import __main__ as entry
from robot_agent.errors import ConfigError, CredentialError


class Entry(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for patch in (
            mock.patch.object(entry.config, "data_folder", return_value=Path(self.folder.name)),
            mock.patch.object(entry, "_configure_log"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_without_configuration_it_does_not_start_and_returns_2(self):
        with mock.patch.object(entry.config, "read_queue_url", side_effect=ConfigError("missing")):
            with self.assertLogs(entry.LOG, logging.ERROR):
                self.assertEqual(entry.main(), 2)

    def test_without_a_credential_it_does_not_start_and_returns_2(self):
        with mock.patch.object(entry.config, "read_queue_url", return_value="https://x"), \
                mock.patch.object(entry.credentials, "read", side_effect=CredentialError("no key")):
            with self.assertLogs(entry.LOG, logging.ERROR):
                self.assertEqual(entry.main(), 2)

    def _with_valid_dependencies(self, run):
        return (
            mock.patch.object(entry.config, "read_queue_url", return_value="https://x"),
            mock.patch.object(entry.credentials, "read", return_value=("ID", "SECRET")),
            mock.patch.object(entry, "SqsClient"),
            mock.patch.object(entry, "run", side_effect=run),
        )

    def test_an_unexpected_error_returns_1_and_does_not_log_the_error_message(self):
        patches = self._with_valid_dependencies(RuntimeError("SECRET-in-the-text"))
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertLogs(entry.LOG, logging.ERROR) as logs:
                self.assertEqual(entry.main(), 1)
        self.assertNotIn("SECRET", "\n".join(logs.output))

    def test_ctrl_c_exits_with_0(self):
        patches = self._with_valid_dependencies(KeyboardInterrupt())
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertLogs(entry.LOG, logging.INFO):
                self.assertEqual(entry.main(), 0)

    def test_builds_the_agent_with_the_real_shutdown_and_the_configured_queue(self):
        patches = self._with_valid_dependencies(None)
        with patches[0], patches[1], patches[2] as queue, patches[3] as run:
            self.assertEqual(entry.main(), 0)
        queue.assert_called_once_with("https://x", "ID", "SECRET")
        deps = run.call_args.args[0]
        self.assertIs(deps.execute, entry.shutdown.execute)
        self.assertIs(deps.queue, queue.return_value)


class ConfigureLog(unittest.TestCase):
    def test_creates_the_folder_and_the_log_file(self):
        with tempfile.TemporaryDirectory() as base:
            target = Path(base) / "data"
            before = list(entry.LOG.handlers)
            level = entry.LOG.level
            try:
                with mock.patch.object(entry.config, "data_folder", return_value=target):
                    entry._configure_log()
                self.assertTrue((target / "agent.log").exists())
            finally:
                for h in entry.LOG.handlers[len(before):]:
                    h.close()
                entry.LOG.handlers[:] = before
                entry.LOG.setLevel(level)


if __name__ == "__main__":
    unittest.main()
