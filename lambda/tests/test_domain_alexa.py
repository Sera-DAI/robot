import unittest

from robot_lambda.domain import alexa

MAC = "00-14-22-01-23-45"


def directive(namespace, name, payload=None, endpoint="pc-principal", correlation="corr-1", version="3"):
    header = {"namespace": namespace, "name": name, "payloadVersion": version, "messageId": "m-1"}
    if correlation:
        header["correlationToken"] = correlation
    body = {"directive": {"header": header, "payload": payload or {}}}
    if endpoint:
        body["directive"]["endpoint"] = {
            "endpointId": endpoint,
            "scope": {"type": "BearerToken", "token": "test-token"},
        }
    return body


class ParseAndRoute(unittest.TestCase):
    def test_known_routes(self):
        cases = {
            ("Alexa.Discovery", "Discover"): alexa.ROUTE_DISCOVERY,
            ("Alexa.Authorization", "AcceptGrant"): alexa.ROUTE_ACCEPT_GRANT,
            ("Alexa.PowerController", "TurnOn"): alexa.ROUTE_TURN_ON,
            ("Alexa.PowerController", "TurnOff"): alexa.ROUTE_TURN_OFF,
            ("Alexa.PowerController", "Other"): alexa.ROUTE_UNKNOWN,
        }
        for (ns, name), route in cases.items():
            with self.subTest(ns=ns, name=name):
                self.assertEqual(alexa.parse(directive(ns, name)).route, route)

    def test_extracted_fields(self):
        d = alexa.parse(directive("Alexa.PowerController", "TurnOn"))
        self.assertEqual(d.endpoint_id, "pc-principal")
        self.assertEqual(d.correlation_token, "corr-1")
        self.assertEqual(d.user_token, "test-token")

    def test_invalid_formats(self):
        for bad in (None, {}, {"directive": 1}, {"directive": {}}, directive("A", "B", version="2")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    alexa.parse(bad)


class Mac(unittest.TestCase):
    def test_accepts_the_hyphen_format_and_normalizes(self):
        self.assertEqual(alexa.validate_mac(MAC.lower()), MAC)

    def test_rejects_other_formats(self):
        for bad in (MAC.replace("-", ":"), "0014.2201.2345", MAC[:-3], "", None, "zz" + MAC[2:]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    alexa.validate_mac(bad)


class Discovery(unittest.TestCase):
    def setUp(self):
        self.response = alexa.discovery("pc-principal", MAC, "m-2")
        self.endpoint = self.response["event"]["payload"]["endpoints"][0]

    def test_header(self):
        h = self.response["event"]["header"]
        self.assertEqual((h["namespace"], h["name"], h["payloadVersion"]), ("Alexa.Discovery", "Discover.Response", "3"))

    def test_a_single_endpoint_called_pc(self):
        self.assertEqual(len(self.response["event"]["payload"]["endpoints"]), 1)
        self.assertEqual(self.endpoint["friendlyName"], "PC")
        self.assertEqual(self.endpoint["endpointId"], "pc-principal")

    def test_declared_interfaces(self):
        interfaces = {c["interface"]: c for c in self.endpoint["capabilities"]}
        self.assertIn("Alexa.PowerController", interfaces)
        self.assertIn("Alexa.WakeOnLANController", interfaces)
        self.assertTrue(all(c["version"] == "3" for c in interfaces.values()))

    def test_mac_in_the_wol_configuration(self):
        wol = next(c for c in self.endpoint["capabilities"] if c["interface"] == "Alexa.WakeOnLANController")
        self.assertEqual(wol["configuration"]["MACAddresses"], [MAC])
        self.assertEqual(wol["properties"], {})

    def test_invalid_mac_fails(self):
        with self.assertRaises(ValueError):
            alexa.discovery("pc-principal", "xx", "m")


class AcceptGrant(unittest.TestCase):
    def test_extracts_the_code(self):
        payload = {"grant": {"type": "OAuth2.AuthorizationCode", "code": "test-code"}}
        self.assertEqual(alexa.extract_grant_code(payload), "test-code")

    def test_invalid_grant(self):
        for bad in ({}, {"grant": {"type": "Other", "code": "x"}}, {"grant": {"type": "OAuth2.AuthorizationCode"}}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    alexa.extract_grant_code(bad)

    def test_responses(self):
        ok = alexa.accept_grant_ok("m")["event"]
        self.assertEqual((ok["header"]["namespace"], ok["header"]["name"]), ("Alexa.Authorization", "AcceptGrant.Response"))
        self.assertEqual(ok["payload"], {})
        error = alexa.accept_grant_error("m")["event"]
        self.assertEqual(error["header"]["name"], "ErrorResponse")
        self.assertEqual(error["payload"]["type"], "ACCEPT_GRANT_FAILED")


class TurnOn(unittest.TestCase):
    def test_deferred_carries_the_same_correlation_token(self):
        e = alexa.deferred("corr-1", "m")["event"]
        self.assertEqual((e["header"]["namespace"], e["header"]["name"]), ("Alexa", "DeferredResponse"))
        self.assertEqual(e["header"]["correlationToken"], "corr-1")

    def test_wakeup_with_scope_and_off_state(self):
        e = alexa.wakeup_event("tok", "pc-principal", "corr-1", "m", "2026-01-01T00:00:00.00Z")
        h = e["event"]["header"]
        self.assertEqual((h["namespace"], h["name"]), ("Alexa.WakeOnLANController", "WakeUp"))
        self.assertEqual(h["correlationToken"], "corr-1")
        self.assertEqual(e["event"]["endpoint"]["scope"], {"type": "BearerToken", "token": "tok"})
        self.assertEqual(e["event"]["endpoint"]["endpointId"], "pc-principal")
        self.assertEqual(e["context"]["properties"][0]["value"], "OFF")

    def test_final_response_with_on_state(self):
        e = alexa.response_event("tok", "pc-principal", "corr-1", "m", "2026-01-01T00:00:00.00Z")
        self.assertEqual((e["event"]["header"]["namespace"], e["event"]["header"]["name"]), ("Alexa", "Response"))
        self.assertEqual(e["context"]["properties"][0]["value"], "ON")

    def test_asynchronous_and_synchronous_errors(self):
        a = alexa.error_event("tok", "pc-principal", "corr-1", "m", alexa.ERROR_INTERNAL, "x")["event"]
        self.assertEqual(a["payload"]["type"], "INTERNAL_ERROR")
        self.assertEqual(a["endpoint"]["scope"]["token"], "tok")
        s = alexa.sync_error("pc-principal", "corr-1", "m", alexa.ERROR_NO_SUCH_ENDPOINT, "x")["event"]
        self.assertNotIn("scope", s["endpoint"])
        self.assertNotIn("endpoint", alexa.sync_error(None, None, "m", alexa.ERROR_INTERNAL, "x")["event"])


if __name__ == "__main__":
    unittest.main()
