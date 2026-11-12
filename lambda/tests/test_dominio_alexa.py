import unittest

from robot_lambda.dominio import alexa

MAC = "00-14-22-01-23-45"


def diretiva(namespace, nome, payload=None, endpoint="pc-principal", correlation="corr-1", versao="3"):
    cabecalho = {"namespace": namespace, "name": nome, "payloadVersion": versao, "messageId": "m-1"}
    if correlation:
        cabecalho["correlationToken"] = correlation
    corpo = {"directive": {"header": cabecalho, "payload": payload or {}}}
    if endpoint:
        corpo["directive"]["endpoint"] = {
            "endpointId": endpoint,
            "scope": {"type": "BearerToken", "token": "token-de-teste"},
        }
    return corpo


class SepararERotear(unittest.TestCase):
    def test_rotas_conhecidas(self):
        casos = {
            ("Alexa.Discovery", "Discover"): alexa.ROTA_DISCOVERY,
            ("Alexa.Authorization", "AcceptGrant"): alexa.ROTA_ACCEPT_GRANT,
            ("Alexa.PowerController", "TurnOn"): alexa.ROTA_LIGAR,
            ("Alexa.PowerController", "TurnOff"): alexa.ROTA_DESLIGAR,
            ("Alexa.PowerController", "Outra"): alexa.ROTA_DESCONHECIDA,
        }
        for (ns, nome), rota in casos.items():
            with self.subTest(ns=ns, nome=nome):
                self.assertEqual(alexa.separar(diretiva(ns, nome)).rota, rota)

    def test_campos_extraidos(self):
        d = alexa.separar(diretiva("Alexa.PowerController", "TurnOn"))
        self.assertEqual(d.endpoint_id, "pc-principal")
        self.assertEqual(d.correlation_token, "corr-1")
        self.assertEqual(d.token_usuario, "token-de-teste")

    def test_formatos_invalidos(self):
        for ruim in (None, {}, {"directive": 1}, {"directive": {}}, diretiva("A", "B", versao="2")):
            with self.subTest(ruim=ruim):
                with self.assertRaises(ValueError):
                    alexa.separar(ruim)


class Mac(unittest.TestCase):
    def test_aceita_formato_com_hifens_e_normaliza(self):
        self.assertEqual(alexa.validar_mac(MAC.lower()), MAC)

    def test_rejeita_outros_formatos(self):
        for ruim in (MAC.replace("-", ":"), "0014.2201.2345", MAC[:-3], "", None, "zz" + MAC[2:]):
            with self.subTest(ruim=ruim):
                with self.assertRaises(ValueError):
                    alexa.validar_mac(ruim)


class Discovery(unittest.TestCase):
    def setUp(self):
        self.resposta = alexa.discovery("pc-principal", MAC, "m-2")
        self.endpoint = self.resposta["event"]["payload"]["endpoints"][0]

    def test_cabecalho(self):
        h = self.resposta["event"]["header"]
        self.assertEqual((h["namespace"], h["name"], h["payloadVersion"]), ("Alexa.Discovery", "Discover.Response", "3"))

    def test_um_unico_endpoint_chamado_pc(self):
        self.assertEqual(len(self.resposta["event"]["payload"]["endpoints"]), 1)
        self.assertEqual(self.endpoint["friendlyName"], "PC")
        self.assertEqual(self.endpoint["endpointId"], "pc-principal")

    def test_interfaces_declaradas(self):
        interfaces = {c["interface"]: c for c in self.endpoint["capabilities"]}
        self.assertIn("Alexa.PowerController", interfaces)
        self.assertIn("Alexa.WakeOnLANController", interfaces)
        self.assertTrue(all(c["version"] == "3" for c in interfaces.values()))

    def test_mac_na_configuracao_do_wol(self):
        wol = next(c for c in self.endpoint["capabilities"] if c["interface"] == "Alexa.WakeOnLANController")
        self.assertEqual(wol["configuration"]["MACAddresses"], [MAC])
        self.assertEqual(wol["properties"], {})

    def test_mac_invalido_falha(self):
        with self.assertRaises(ValueError):
            alexa.discovery("pc-principal", "xx", "m")


class AcceptGrant(unittest.TestCase):
    def test_extrai_codigo(self):
        payload = {"grant": {"type": "OAuth2.AuthorizationCode", "code": "codigo-de-teste"}}
        self.assertEqual(alexa.extrair_codigo_grant(payload), "codigo-de-teste")

    def test_grant_invalido(self):
        for ruim in ({}, {"grant": {"type": "Outro", "code": "x"}}, {"grant": {"type": "OAuth2.AuthorizationCode"}}):
            with self.subTest(ruim=ruim):
                with self.assertRaises(ValueError):
                    alexa.extrair_codigo_grant(ruim)

    def test_respostas(self):
        ok = alexa.accept_grant_ok("m")["event"]
        self.assertEqual((ok["header"]["namespace"], ok["header"]["name"]), ("Alexa.Authorization", "AcceptGrant.Response"))
        self.assertEqual(ok["payload"], {})
        erro = alexa.accept_grant_erro("m")["event"]
        self.assertEqual(erro["header"]["name"], "ErrorResponse")
        self.assertEqual(erro["payload"]["type"], "ACCEPT_GRANT_FAILED")


class TurnOn(unittest.TestCase):
    def test_deferred_leva_o_mesmo_correlation_token(self):
        e = alexa.deferred("corr-1", "m")["event"]
        self.assertEqual((e["header"]["namespace"], e["header"]["name"]), ("Alexa", "DeferredResponse"))
        self.assertEqual(e["header"]["correlationToken"], "corr-1")

    def test_wakeup_com_escopo_e_estado_off(self):
        e = alexa.evento_wakeup("tok", "pc-principal", "corr-1", "m", "2026-01-01T00:00:00.00Z")
        h = e["event"]["header"]
        self.assertEqual((h["namespace"], h["name"]), ("Alexa.WakeOnLANController", "WakeUp"))
        self.assertEqual(h["correlationToken"], "corr-1")
        self.assertEqual(e["event"]["endpoint"]["scope"], {"type": "BearerToken", "token": "tok"})
        self.assertEqual(e["event"]["endpoint"]["endpointId"], "pc-principal")
        self.assertEqual(e["context"]["properties"][0]["value"], "OFF")

    def test_resposta_final_com_estado_on(self):
        e = alexa.evento_resposta("tok", "pc-principal", "corr-1", "m", "2026-01-01T00:00:00.00Z")
        self.assertEqual((e["event"]["header"]["namespace"], e["event"]["header"]["name"]), ("Alexa", "Response"))
        self.assertEqual(e["context"]["properties"][0]["value"], "ON")

    def test_erro_assincrono_e_sincrono(self):
        a = alexa.evento_erro("tok", "pc-principal", "corr-1", "m", alexa.ERRO_INTERNO, "x")["event"]
        self.assertEqual(a["payload"]["type"], "INTERNAL_ERROR")
        self.assertEqual(a["endpoint"]["scope"]["token"], "tok")
        s = alexa.erro_sincrono("pc-principal", "corr-1", "m", alexa.ERRO_ENDPOINT_INEXISTENTE, "x")["event"]
        self.assertNotIn("scope", s["endpoint"])
        self.assertNotIn("endpoint", alexa.erro_sincrono(None, None, "m", alexa.ERRO_INTERNO, "x")["event"])


if __name__ == "__main__":
    unittest.main()
