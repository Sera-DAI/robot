import os
import unittest
from unittest import mock

from robot_lambda import handler

ENVIRONMENT = {
    "ROBOT_MAC": "00-14-22-01-23-45",
    "TOKENS_TABLE": "test-table",
    "LWA_CLIENT_ID": "test-id",
    "LWA_CLIENT_SECRET": "test-secret",
    "AWS_LAMBDA_FUNCTION_NAME": "test-function",
    "QUEUE_URL": "https://queue.invalid/test",
}


_REAL_BUILD = handler._build


class Handler(unittest.TestCase):
    def setUp(self):
        handler._deps = None
        self.addCleanup(setattr, handler, "_deps", None)

    def _build_without_sdk(self):
        with mock.patch.dict(os.environ, ENVIRONMENT, clear=True), \
                mock.patch.object(handler, "DynamoTokens"), \
                mock.patch.object(handler, "LambdaInvoker"), \
                mock.patch.object(handler, "SqsQueue"):
            return _REAL_BUILD()

    def test_builds_the_dependencies_from_the_environment(self):
        deps = self._build_without_sdk()
        self.assertEqual(deps.config.mac, ENVIRONMENT["ROBOT_MAC"])
        self.assertEqual(deps.config.endpoint_id, "pc-principal")
        self.assertRegex(deps.now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.00Z$")
        self.assertNotEqual(deps.new_id(), deps.new_id())

    def test_a_missing_required_variable_fails_loudly(self):
        for missing in ENVIRONMENT:
            with self.subTest(missing=missing):
                environment = {k: v for k, v in ENVIRONMENT.items() if k != missing}
                with mock.patch.dict(os.environ, environment, clear=True), \
                        mock.patch.object(handler, "DynamoTokens"), \
                        mock.patch.object(handler, "LambdaInvoker"), \
                        mock.patch.object(handler, "SqsQueue"):
                    with self.assertRaises(KeyError):
                        handler._build()

    def test_handle_caches_the_dependencies_and_answers_discovery(self):
        event = {
            "directive": {
                "header": {"namespace": "Alexa.Discovery", "name": "Discover", "payloadVersion": "3", "messageId": "m"},
                "payload": {"scope": {"type": "BearerToken", "token": "test-token"}},
            }
        }
        with mock.patch.object(handler, "_build", side_effect=lambda: self._build_without_sdk()) as build:
            r1 = handler.handle(event, None)
            handler.handle(event, None)
        self.assertEqual(build.call_count, 1)
        self.assertEqual(r1["event"]["header"]["name"], "Discover.Response")


if __name__ == "__main__":
    unittest.main()
