import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from robot_agent import config
from robot_agent.adapters import shutdown, sigv4, sqs
from robot_agent.errors import ConfigError, QueueError, ShutdownError

# Example values from the AWS documentation, not real credentials.
EXAMPLE_ID = "AKIDEXAMPLE"
EXAMPLE_SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
URL = "https://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos"
INSTANT = "20260101T000000Z"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SigV4(unittest.TestCase):
    def test_signing_key_matches_the_documentation_example(self):
        key = sigv4.signing_key(EXAMPLE_SECRET, "20120215", "us-east-1", "iam")
        self.assertEqual(key.hex(), "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d")

    def test_signature_of_a_fixed_request_does_not_change(self):
        # Value checked against botocore (SigV4Auth) outside the repository.
        headers = sigv4.sign_post(
            host="sqs.us-east-1.amazonaws.com", path="/", body=b'{"QueueUrl": "x"}',
            headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AmazonSQS.ReceiveMessage"},
            key_id=EXAMPLE_ID, secret=EXAMPLE_SECRET, region="us-east-1", service="sqs", instant=INSTANT,
        )
        self.assertEqual(
            headers["authorization"],
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20260101/us-east-1/sqs/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date;x-amz-target, "
            "Signature=4e84c39671b14c14a14bf11c6e36e7252a38548f09e549ba410d41012ca4b28f",
        )
        self.assertNotIn(EXAMPLE_SECRET, json.dumps(headers))


class Sqs(unittest.TestCase):
    def setUp(self):
        self.client = sqs.SqsClient(URL, EXAMPLE_ID, EXAMPLE_SECRET, now_amz=lambda: INSTANT)

    def test_queue_url_can_only_be_aws_sqs(self):
        self.assertEqual(sqs.region_from_url(URL), "us-east-1")
        bad_urls = [
            "http://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos",
            "https://sqs.us-east-1.amazonaws.com.example.invalid/000000000000/robot-comandos",
            "https://example.invalid/000000000000/robot-comandos",
            "https://sqs.us-east-1.amazonaws.com/000000000000/robot-comandos?x=1",
            "https://sqs.us-east-1.amazonaws.com/abc/robot-comandos",
            "", None,
        ]
        for bad in bad_urls:
            with self.subTest(bad=bad), self.assertRaises(QueueError):
                sqs.region_from_url(bad)

    def test_receive_builds_the_request_and_reads_the_messages(self):
        body = json.dumps({"Messages": [
            {"MessageId": "1", "ReceiptHandle": "receipt-1", "Body": '{"version": 1, "action": "shutdown"}',
             "Attributes": {"SentTimestamp": "1000000001000"}},
            {"MessageId": "2", "ReceiptHandle": "receipt-2", "Body": "x"},
            {"MessageId": "3"},
        ]}).encode()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)) as urlopen:
            messages = self.client.receive()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://sqs.us-east-1.amazonaws.com/")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-amz-target"), "AmazonSQS.ReceiveMessage")
        self.assertTrue(request.get_header("Authorization").startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/"))
        sent = json.loads(request.data)
        self.assertEqual(sent["QueueUrl"], URL)
        self.assertEqual(sent["WaitTimeSeconds"], 20)
        self.assertGreater(urlopen.call_args.kwargs["timeout"], 20)
        self.assertEqual(
            messages,
            [
                sqs.Message('{"version": 1, "action": "shutdown"}', "receipt-1", 1000000001000),
                sqs.Message("x", "receipt-2", None),
            ],
        )

    def test_empty_queue_returns_an_empty_list(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"{}")):
            self.assertEqual(self.client.receive(), [])

    def test_delete_sends_the_receipt(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"")) as urlopen:
            self.client.delete("receipt-1")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-amz-target"), "AmazonSQS.DeleteMessage")
        self.assertEqual(json.loads(request.data), {"QueueUrl": URL, "ReceiptHandle": "receipt-1"})

    def test_errors_leak_neither_secret_nor_body(self):
        http = urllib.error.HTTPError(URL, 403, "x", {}, io.BytesIO(("contains " + EXAMPLE_SECRET).encode()))
        for failure in (http, OSError("contains " + EXAMPLE_SECRET)):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch("urllib.request.urlopen", side_effect=failure), self.assertRaises(QueueError) as error:
                    self.client.receive()
                self.assertNotIn(EXAMPLE_SECRET, str(error.exception))
                self.assertIsNone(error.exception.__cause__)

    def test_a_response_that_is_not_json_becomes_an_error(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"<html>")), self.assertRaises(QueueError):
            self.client.receive()


class Shutdown(unittest.TestCase):
    """subprocess is always replaced: no test shuts any machine down."""

    def test_calls_windows_shutdown_with_fixed_arguments_and_no_shell(self):
        with mock.patch.object(shutdown.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            shutdown.execute("shutdown")
        arguments = run.call_args.args[0]
        self.assertTrue(arguments[0].lower().endswith("shutdown.exe"))
        self.assertEqual(arguments[1:4], ["/s", "/t", "30"])
        self.assertIs(run.call_args.kwargs["shell"], False)

    def test_an_action_outside_the_list_never_reaches_subprocess(self):
        with mock.patch.object(shutdown.subprocess, "run") as run:
            for bad in ("reboot", "calc.exe", "", "shutdown /r", None):
                with self.subTest(bad=bad), self.assertRaises(ShutdownError):
                    shutdown.execute(bad)
        run.assert_not_called()

    def test_windows_refusal_becomes_an_error(self):
        with mock.patch.object(shutdown.subprocess, "run", return_value=mock.Mock(returncode=5)):
            with self.assertRaises(ShutdownError):
                shutdown.execute("shutdown")
        with mock.patch.object(shutdown.subprocess, "run", side_effect=OSError("x")):
            with self.assertRaises(ShutdownError):
                shutdown.execute("shutdown")


class Config(unittest.TestCase):
    def test_writes_and_reads_the_queue_url(self):
        with tempfile.TemporaryDirectory() as folder:
            config.write_queue_url(URL, Path(folder) / "data")
            self.assertEqual(config.read_queue_url(Path(folder) / "data"), URL)

    def test_reads_the_key_written_by_earlier_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / config.FILE).write_text(json.dumps({config.LEGACY_KEY: URL}), encoding="utf-8")
            self.assertEqual(config.read_queue_url(Path(folder)), URL)

    def test_missing_or_invalid_config_becomes_a_clear_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ConfigError):
                config.read_queue_url(Path(folder))
            for content in ("junk", "[]", '{"other": 1}', '{"queue_url": 5}', '{"fila_url": 5}'):
                (Path(folder) / config.FILE).write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ConfigError):
                    config.read_queue_url(Path(folder))


if __name__ == "__main__":
    unittest.main()
