import unittest

from robot_agent.domain import commands

START = 1_000_000_000_000


class Interpret(unittest.TestCase):
    def test_accepts_only_the_exact_command(self):
        self.assertEqual(commands.interpret('{"version": 1, "action": "shutdown"}'), "shutdown")

    def test_refuses_everything_outside_the_fixed_list(self):
        bad_inputs = [
            None, 42, b'{"version": 1, "action": "shutdown"}', "", "shutdown", "not json", "[]", '"shutdown"',
            '{"action": "shutdown"}',
            '{"version": 2, "action": "shutdown"}',
            '{"version": "1", "action": "shutdown"}',
            '{"version": true, "action": "shutdown"}',
            '{"version": 1, "action": "reboot"}',
            '{"version": 1, "action": "Shutdown"}',
            '{"version": 1, "action": "shutdown /r"}',
            '{"version": 1, "action": ["shutdown"]}',
            '{"version": 1, "action": "shutdown", "command": "calc.exe"}',
            '{"version": 1, "action": "shutdown", "x": "' + "a" * 300 + '"}',
        ]
        for bad in bad_inputs:
            with self.subTest(bad=bad):
                self.assertIsNone(commands.interpret(bad))

    def test_the_list_is_fixed(self):
        self.assertEqual(commands.ACTIONS, frozenset({"shutdown"}))


class Validity(unittest.TestCase):
    def test_a_recent_command_sent_after_startup_is_valid(self):
        self.assertTrue(commands.is_valid(START + 1_000, START + 2_000, START))
        self.assertTrue(commands.is_valid(START, START + 60_000, START))

    def test_a_command_sent_before_the_agent_started_is_not_valid(self):
        self.assertFalse(commands.is_valid(START - 1, START + 500, START))

    def test_an_old_command_is_not_valid(self):
        self.assertFalse(commands.is_valid(START, START + 60_001, START))

    def test_without_a_send_time_it_is_not_valid(self):
        for bad in (None, "1000000000000", 1.5, True):
            with self.subTest(bad=bad):
                self.assertFalse(commands.is_valid(bad, START, 0))


if __name__ == "__main__":
    unittest.main()
