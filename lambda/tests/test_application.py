import itertools
import unittest

from robot_lambda import application
from robot_lambda.application import Config, Deps, process
from robot_lambda.errors import GatewayError, InvocationError, LwaError, QueueError, StorageError

MAC = "00-14-22-01-23-45"
CLIENT_SECRET = "test-client-secret"
TOKEN = "test-access-token"
REFRESH = "test-refresh"
CODE = "test-code"
NOW = 1_000_000.0


class FakeTokens:
    def __init__(self, record=None, fail=False):
        self.record, self.fail = record, fail

    def get(self):
        if self.fail:
            raise StorageError("x")
        return self.record

    def save(self, record):
        if self.fail:
            raise StorageError("x")
        self.record = record


class FakeLwa:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def exchange_code(self, code):
        self.calls.append(("code", code))
        if self.fail:
            raise LwaError("x")
        return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}

    def renew(self, refresh):
        self.calls.append(("refresh", refresh))
        if self.fail:
            raise LwaError("x")
        return {"access_token": "renewed", "refresh_token": "renewed-refresh", "expires_in": 3600}


class FakeGateway:
    def __init__(self, fail_at=()):
        self.sent, self.fail_at = [], set(fail_at)

    def send(self, event):
        index = len(self.sent)
        self.sent.append(event)
        if index in self.fail_at:
            raise GatewayError("x")


class FakeInvoker:
    def __init__(self, fail=False):
        self.payloads, self.fail = [], fail

    def trigger(self, payload):
        if self.fail:
            raise InvocationError("x")
        self.payloads.append(payload)


class FakeQueue:
    def __init__(self, fail=False):
        self.commands, self.fail = [], fail

    def send(self, command):
        if self.fail:
            raise QueueError("x")
        self.commands.append(command)


def build(tokens=None, lwa=None, gateway=None, invoker=None, queue=None):
    counter = itertools.count(1)
    return Deps(
        config=Config(endpoint_id="pc-principal", mac=MAC),
        tokens=tokens or FakeTokens(),
        lwa=lwa or FakeLwa(),
        gateway=gateway or FakeGateway(),
        invoker=invoker or FakeInvoker(),
        queue=queue or FakeQueue(),
        now=lambda: NOW,
        now_iso=lambda: "2026-01-01T00:00:00.00Z",
        new_id=lambda: f"id-{next(counter)}",
    )


def directive(namespace, name, payload=None, endpoint="pc-principal"):
    body = {
        "directive": {
            "header": {"namespace": namespace, "name": name, "payloadVersion": "3",
                       "messageId": "m", "correlationToken": "corr-1"},
            "payload": payload or {},
        }
    }
    if endpoint:
        body["directive"]["endpoint"] = {"endpointId": endpoint, "scope": {"type": "BearerToken", "token": TOKEN}}
    return body


def record(expires_at=NOW + 3600):
    return {"access_token": TOKEN, "refresh_token": REFRESH, "expires_at": int(expires_at)}


class Routing(unittest.TestCase):
    def test_discovery(self):
        r = process(directive("Alexa.Discovery", "Discover", endpoint=None), build())
        self.assertEqual(r["event"]["header"]["name"], "Discover.Response")

    def test_discovery_with_wrong_configured_mac_becomes_an_error_without_leaking_the_value(self):
        d = build()
        d.config.mac = "wrong-mac"
        with self.assertLogs(application.LOG, level="DEBUG") as captured:
            r = process(directive("Alexa.Discovery", "Discover", endpoint=None), d)
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")
        self.assertNotIn("wrong-mac", "\n".join(captured.output))

    def test_invalid_event_becomes_an_error_without_raising(self):
        r = process({"anything": "else"}, build())
        self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_event_that_is_not_a_dict_does_not_raise(self):
        for bad in (None, [], "text", 42):
            with self.subTest(bad=bad):
                r = process(bad, build())
                self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_turnon_without_correlation_token(self):
        d = build()
        event = directive("Alexa.PowerController", "TurnOn")
        del event["directive"]["header"]["correlationToken"]
        r = process(event, d)
        self.assertNotIn("correlationToken", r["event"]["header"])
        self.assertIsNone(d.invoker.payloads[0]["robot_internal"]["correlationToken"])

    def test_unknown_directive(self):
        r = process(directive("Alexa.Other", "Do"), build())
        self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_turnoff_queues_shutdown_and_answers_off_immediately(self):
        d = build()
        r = process(directive("Alexa.PowerController", "TurnOff"), d)
        self.assertEqual(d.queue.commands, [{"version": 1, "action": "shutdown"}])
        self.assertEqual(r["event"]["header"]["name"], "Response")
        self.assertEqual(r["event"]["header"]["correlationToken"], "corr-1")
        self.assertEqual(r["event"]["endpoint"]["endpointId"], "pc-principal")
        self.assertEqual(r["context"]["properties"][0]["value"], "OFF")
        self.assertEqual(d.invoker.payloads, [])
        self.assertEqual(d.gateway.sent, [])

    def test_turnoff_for_unknown_endpoint_queues_nothing(self):
        d = build()
        r = process(directive("Alexa.PowerController", "TurnOff", endpoint="other"), d)
        self.assertEqual(r["event"]["payload"]["type"], "NO_SUCH_ENDPOINT")
        self.assertEqual(d.queue.commands, [])

    def test_turnoff_with_queue_failure_becomes_an_error(self):
        d = build(queue=FakeQueue(fail=True))
        r = process(directive("Alexa.PowerController", "TurnOff"), d)
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")

    def test_turnon_queues_nothing(self):
        d = build()
        process(directive("Alexa.PowerController", "TurnOn"), d)
        self.assertEqual(d.queue.commands, [])

    def test_internal_payload_is_ignored_inside_an_alexa_directive(self):
        d = build(tokens=FakeTokens(record()))
        event = directive("Alexa.Other", "Do")
        event["robot_internal"] = {"action": "turn_on", "endpointId": "pc-principal"}
        process(event, d)
        self.assertEqual(d.gateway.sent, [])


class AcceptGrant(unittest.TestCase):
    def payload(self):
        return {"grant": {"type": "OAuth2.AuthorizationCode", "code": CODE}, "grantee": {"type": "BearerToken", "token": TOKEN}}

    def test_exchanges_the_code_and_stores_the_tokens(self):
        d = build()
        r = process(directive("Alexa.Authorization", "AcceptGrant", self.payload(), endpoint=None), d)
        self.assertEqual(r["event"]["header"]["name"], "AcceptGrant.Response")
        self.assertEqual(d.lwa.calls, [("code", CODE)])
        self.assertEqual(
            d.tokens.record,
            {"access_token": "new-access", "refresh_token": "new-refresh", "expires_at": int(NOW) + 3600},
        )

    def test_failures_become_accept_grant_failed(self):
        cases = {
            "lwa": build(lwa=FakeLwa(fail=True)),
            "storage": build(tokens=FakeTokens(fail=True)),
        }
        for name, d in cases.items():
            with self.subTest(name):
                r = process(directive("Alexa.Authorization", "AcceptGrant", self.payload(), endpoint=None), d)
                self.assertEqual(r["event"]["payload"]["type"], "ACCEPT_GRANT_FAILED")

    def test_grant_without_code(self):
        r = process(directive("Alexa.Authorization", "AcceptGrant", {}, endpoint=None), build())
        self.assertEqual(r["event"]["payload"]["type"], "ACCEPT_GRANT_FAILED")


class TurnOnSynchronous(unittest.TestCase):
    def test_answers_deferred_and_triggers_the_internal_invocation(self):
        d = build()
        r = process(directive("Alexa.PowerController", "TurnOn"), d)
        self.assertEqual(r["event"]["header"]["name"], "DeferredResponse")
        self.assertEqual(r["event"]["header"]["correlationToken"], "corr-1")
        self.assertEqual(
            d.invoker.payloads,
            [{"robot_internal": {"action": "turn_on", "endpointId": "pc-principal", "correlationToken": "corr-1"}}],
        )
        self.assertEqual(d.gateway.sent, [], "no event may go out before the synchronous response")

    def test_unknown_endpoint(self):
        d = build()
        r = process(directive("Alexa.PowerController", "TurnOn", endpoint="other"), d)
        self.assertEqual(r["event"]["payload"]["type"], "NO_SUCH_ENDPOINT")
        self.assertEqual(d.invoker.payloads, [])

    def test_failure_to_schedule_becomes_an_internal_error(self):
        r = process(directive("Alexa.PowerController", "TurnOn"), build(invoker=FakeInvoker(fail=True)))
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")


def internal_payload(**extra):
    base = {"action": "turn_on", "endpointId": "pc-principal", "correlationToken": "corr-1"}
    base.update(extra)
    return {"robot_internal": base}


class TurnOnAsynchronous(unittest.TestCase):
    def test_sends_wakeup_then_the_final_response(self):
        d = build(tokens=FakeTokens(record()))
        r = process(internal_payload(), d)
        self.assertEqual(r, {"ok": True})
        names = [e["event"]["header"]["name"] for e in d.gateway.sent]
        self.assertEqual(names, ["WakeUp", "Response"])
        for e in d.gateway.sent:
            self.assertEqual(e["event"]["header"]["correlationToken"], "corr-1")
            self.assertEqual(e["event"]["endpoint"]["scope"]["token"], TOKEN)
        self.assertEqual(d.lwa.calls, [])

    def test_renews_a_token_close_to_expiry_and_stores_it(self):
        d = build(tokens=FakeTokens(record(expires_at=NOW + 10)))
        process(internal_payload(), d)
        self.assertEqual(d.lwa.calls, [("refresh", REFRESH)])
        self.assertEqual(d.gateway.sent[0]["event"]["endpoint"]["scope"]["token"], "renewed")
        self.assertEqual(d.tokens.record["refresh_token"], "renewed-refresh")

    def test_exact_renewal_margin(self):
        cases = {
            NOW + application.RENEWAL_MARGIN_S: True,
            NOW + application.RENEWAL_MARGIN_S + 1: False,
        }
        for expires_at, should_renew in cases.items():
            with self.subTest(expires_at=expires_at):
                d = build(tokens=FakeTokens(record(expires_at=expires_at)))
                process(internal_payload(), d)
                self.assertEqual(bool(d.lwa.calls), should_renew)

    def test_renewal_without_a_new_refresh_token_keeps_the_previous_one(self):
        class LwaWithoutRefresh(FakeLwa):
            def renew(self, refresh):
                self.calls.append(("refresh", refresh))
                return {"access_token": "renewed", "expires_in": 3600}

        d = build(tokens=FakeTokens(record(expires_at=NOW)), lwa=LwaWithoutRefresh())
        process(internal_payload(), d)
        self.assertEqual(d.tokens.record["refresh_token"], REFRESH)
        self.assertEqual(d.tokens.record["access_token"], "renewed")

    def test_without_a_correlation_token_the_events_go_out_without_the_field(self):
        d = build(tokens=FakeTokens(record()))
        process({"robot_internal": {"action": "turn_on", "endpointId": "pc-principal", "correlationToken": None}}, d)
        for e in d.gateway.sent:
            self.assertNotIn("correlationToken", e["event"]["header"])

    def test_failure_on_the_final_response_still_warns_alexa(self):
        d = build(tokens=FakeTokens(record()), gateway=FakeGateway(fail_at={1}))
        self.assertEqual(process(internal_payload(), d)["reason"], "gateway")
        names = [e["event"]["header"]["name"] for e in d.gateway.sent]
        self.assertEqual(names, ["WakeUp", "Response", "ErrorResponse"])

    def test_failure_even_on_the_error_warning_does_not_raise(self):
        d = build(tokens=FakeTokens(record()), gateway=FakeGateway(fail_at={0, 1}))
        self.assertEqual(process(internal_payload(), d)["reason"], "gateway")
        self.assertEqual(len(d.gateway.sent), 2)

    def test_no_tokens_sends_nothing(self):
        d = build(tokens=FakeTokens(None))
        self.assertEqual(process(internal_payload(), d), {"ok": False, "reason": "no_token"})
        self.assertEqual(d.gateway.sent, [])

    def test_renewal_failure_sends_nothing(self):
        d = build(tokens=FakeTokens(record(expires_at=NOW)), lwa=FakeLwa(fail=True))
        self.assertEqual(process(internal_payload(), d)["reason"], "no_token")
        self.assertEqual(d.gateway.sent, [])

    def test_failure_on_wakeup_warns_alexa_of_the_error_and_skips_the_final_response(self):
        d = build(tokens=FakeTokens(record()), gateway=FakeGateway(fail_at={0}))
        self.assertEqual(process(internal_payload(), d)["reason"], "gateway")
        names = [e["event"]["header"]["name"] for e in d.gateway.sent]
        self.assertEqual(names, ["WakeUp", "ErrorResponse"])

    def test_invalid_payloads_are_discarded(self):
        for bad in (internal_payload(action="turn_off"), internal_payload(endpointId="other"), {"robot_internal": "x"}):
            with self.subTest(bad=bad):
                d = build(tokens=FakeTokens(record()))
                self.assertFalse(process(bad, d)["ok"])
                self.assertEqual(d.gateway.sent, [])


class LogsWithoutSecrets(unittest.TestCase):
    def test_no_log_carries_a_token_code_or_secret(self):
        scenarios = [
            lambda: process(directive("Alexa.PowerController", "TurnOn"), build()),
            lambda: process(internal_payload(), build(tokens=FakeTokens(record()))),
            lambda: process(internal_payload(), build(tokens=FakeTokens(record()), gateway=FakeGateway(fail_at={0, 1}))),
            lambda: process(internal_payload(), build(tokens=FakeTokens(record(NOW)), lwa=FakeLwa(fail=True))),
            lambda: process(
                directive("Alexa.Authorization", "AcceptGrant",
                          {"grant": {"type": "OAuth2.AuthorizationCode", "code": CODE}}, endpoint=None),
                build(lwa=FakeLwa(fail=True)),
            ),
            lambda: process({"directive": {"token": TOKEN}}, build()),
        ]
        for scenario in scenarios:
            with self.assertLogs(application.LOG, level="DEBUG") as captured:
                scenario()
            text = "\n".join(captured.output)
            for forbidden in (TOKEN, REFRESH, CODE, CLIENT_SECRET, "new-access", "renewed"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
