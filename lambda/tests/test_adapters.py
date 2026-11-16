import io
import json
import unittest
import urllib.error
from decimal import Decimal
from unittest import mock

from robot_lambda.adapters import gateway, invoker, lwa, queue, tokens
from robot_lambda.errors import GatewayError, InvocationError, LwaError, QueueError, StorageError

SECRET = "test-client-secret"
CODE = "test-code"


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"{}", status=200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(status, body=b'{"detail": "contains test-client-secret"}'):
    return urllib.error.HTTPError("https://example.invalid", status, "x", {}, io.BytesIO(body))


class Lwa(unittest.TestCase):
    def setUp(self):
        self.client = lwa.LwaClient("test-client-id", SECRET)

    def test_code_exchange_builds_the_request_and_normalizes_the_response(self):
        resposta = FakeResponse(json.dumps({"access_token": "a", "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"}).encode())
        with mock.patch("urllib.request.urlopen", return_value=resposta) as urlopen:
            data = self.client.exchange_code(CODE)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, lwa.TOKEN_URL)
        self.assertEqual(request.get_method(), "POST")
        body = request.data.decode()
        for expected in ("grant_type=authorization_code", f"code={CODE}", "client_id=", "client_secret="):
            self.assertIn(expected, body)
        self.assertEqual(data, {"access_token": "a", "refresh_token": "r", "expires_in": 3600})

    def test_renewal_uses_the_refresh_token(self):
        resposta = FakeResponse(json.dumps({"access_token": "a", "refresh_token": "r", "expires_in": 3600}).encode())
        with mock.patch("urllib.request.urlopen", return_value=resposta) as urlopen:
            self.client.renew("refresh-x")
        body = urlopen.call_args.args[0].data.decode()
        self.assertIn("grant_type=refresh_token", body)
        self.assertIn("refresh_token=refresh-x", body)

    def test_erro_http_nao_vaza_body_nem_segredo(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(400)):
            with self.assertRaises(LwaError) as ctx:
                self.client.exchange_code(CODE)
        self.assertIn("400", str(ctx.exception))
        for forbidden in (SECRET, CODE, "detail"):
            self.assertNotIn(forbidden, str(ctx.exception))

    def test_network_failure_and_incomplete_response(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(LwaError):
                self.client.renew("r")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b'{"access_token": "a"}')):
            with self.assertRaises(LwaError):
                self.client.renew("r")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"not-json")):
            with self.assertRaises(LwaError):
                self.client.renew("r")


class Gateway(unittest.TestCase):
    def test_sends_json_by_post(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"", 202)) as urlopen:
            gateway.GatewayClient().send({"event": {"x": 1}})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, gateway.GATEWAY_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"event": {"x": 1}})

    def test_erros_nao_vazam_body(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(403)):
            with self.assertRaises(GatewayError) as ctx:
                gateway.GatewayClient().send({"event": {"token": "test-token"}})
        self.assertIn("403", str(ctx.exception))
        self.assertNotIn("test-token", str(ctx.exception))
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            with self.assertRaises(GatewayError):
                gateway.GatewayClient().send({})


class FakeTable:
    def __init__(self, item=None, fail=False):
        self.item, self.fail, self.written = item, fail, None

    def get_item(self, Key):
        if self.fail:
            raise RuntimeError("internal detail with test-token")
        return {"Item": self.item} if self.item else {}

    def put_item(self, Item):
        if self.fail:
            raise RuntimeError("internal detail with test-token")
        self.written = Item


class FakeResource:
    def __init__(self, table):
        self.table = table

    def Table(self, name):
        return self.table


class Tokens(unittest.TestCase):
    def test_round_trip(self):
        table = FakeTable()
        repository = tokens.DynamoTokens("t", FakeResource(table))
        repository.save({"access_token": "a", "refresh_token": "r", "expires_at": 10})
        self.assertEqual(table.written, {"id": tokens.RECORD_ID, "access_token": "a", "refresh_token": "r", "expira_em": 10})
        table.item = table.written
        self.assertEqual(repository.get(), {"access_token": "a", "refresh_token": "r", "expires_at": 10})

    def test_reads_a_dynamodb_decimal_as_an_int(self):
        item = {"id": tokens.RECORD_ID, "access_token": "a", "refresh_token": "r", "expira_em": Decimal("123")}
        read_back = tokens.DynamoTokens("t", FakeResource(FakeTable(item))).get()
        self.assertEqual(read_back["expires_at"], 123)
        self.assertIsInstance(read_back["expires_at"], int)

    def test_incomplete_item_becomes_a_project_error(self):
        item = {"id": tokens.RECORD_ID, "access_token": "a", "expira_em": Decimal("1")}
        with self.assertRaises(StorageError):
            tokens.DynamoTokens("t", FakeResource(FakeTable(item))).get()

    def test_empty_returns_none(self):
        self.assertIsNone(tokens.DynamoTokens("t", FakeResource(FakeTable())).get())

    def test_database_error_does_not_leak_detail(self):
        repository = tokens.DynamoTokens("t", FakeResource(FakeTable(fail=True)))
        for call in (repository.get, lambda: repository.save({"access_token": "a", "refresh_token": "r", "expires_at": 1})):
            with self.assertRaises(StorageError) as ctx:
                call()
            self.assertNotIn("test-token", str(ctx.exception))


class Invoker(unittest.TestCase):
    def test_asynchronous_invocation(self):
        client = mock.Mock()
        invoker.LambdaInvoker("function", client).trigger({"a": 1})
        arguments = client.invoke.call_args.kwargs
        self.assertEqual(arguments["InvocationType"], "Event")
        self.assertEqual(arguments["FunctionName"], "function")
        self.assertEqual(json.loads(arguments["Payload"]), {"a": 1})

    def test_fail_vira_erro_do_projeto(self):
        client = mock.Mock()
        client.invoke.side_effect = RuntimeError("detail")
        with self.assertRaises(InvocationError):
            invoker.LambdaInvoker("function", client).trigger({})


class Queue(unittest.TestCase):
    def test_sends_the_command_as_json_to_the_configured_url(self):
        client = mock.Mock()
        queue.SqsQueue("https://queue.invalid/test", client).send({"version": 1, "action": "shutdown"})
        call = client.send_message.call_args.kwargs
        self.assertEqual(call["QueueUrl"], "https://queue.invalid/test")
        self.assertEqual(json.loads(call["MessageBody"]), {"version": 1, "action": "shutdown"})

    def test_fail_do_sdk_vira_erro_sem_detalhe(self):
        client = mock.Mock()
        client.send_message.side_effect = RuntimeError("contains " + SECRET)
        with self.assertRaises(QueueError) as error:
            queue.SqsQueue("https://queue.invalid/test", client).send({"action": "shutdown"})
        self.assertNotIn(SECRET, str(error.exception))
        self.assertIsNone(error.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
