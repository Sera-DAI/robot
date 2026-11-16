import unittest

from robot_lambda.domain import commands


class Commands(unittest.TestCase):
    def test_builds_the_shutdown(self):
        self.assertEqual(commands.build("shutdown"), {"version": 1, "action": "shutdown"})

    def test_refuses_an_action_outside_the_list(self):
        for bad in ("reboot", "", "Shutdown", "shutdown /s", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                commands.build(bad)

    def test_the_list_is_fixed(self):
        self.assertEqual(commands.ACTIONS, frozenset({"shutdown"}))


if __name__ == "__main__":
    unittest.main()
