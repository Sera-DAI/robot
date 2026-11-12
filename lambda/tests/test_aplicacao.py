import itertools
import unittest

from robot_lambda import aplicacao
from robot_lambda.aplicacao import Config, Deps, processar
from robot_lambda.erros import ArmazenamentoErro, FilaErro, GatewayErro, InvocacaoErro, LwaErro

MAC = "00-14-22-01-23-45"
SEGREDO_CLIENTE = "segredo-do-cliente-de-teste"
TOKEN = "token-de-acesso-de-teste"
REFRESH = "refresh-de-teste"
CODIGO = "codigo-de-teste"
AGORA = 1_000_000.0


class TokensFalso:
    def __init__(self, registro=None, falha=False):
        self.registro, self.falha = registro, falha

    def obter(self):
        if self.falha:
            raise ArmazenamentoErro("x")
        return self.registro

    def salvar(self, registro):
        if self.falha:
            raise ArmazenamentoErro("x")
        self.registro = registro


class LwaFalso:
    def __init__(self, falha=False):
        self.chamadas, self.falha = [], falha

    def trocar_codigo(self, codigo):
        self.chamadas.append(("codigo", codigo))
        if self.falha:
            raise LwaErro("x")
        return {"access_token": "novo-acesso", "refresh_token": "novo-refresh", "expires_in": 3600}

    def renovar(self, refresh):
        self.chamadas.append(("refresh", refresh))
        if self.falha:
            raise LwaErro("x")
        return {"access_token": "renovado", "refresh_token": "renovado-refresh", "expires_in": 3600}


class GatewayFalso:
    def __init__(self, falhar_em=()):
        self.enviados, self.falhar_em = [], set(falhar_em)

    def enviar(self, evento):
        indice = len(self.enviados)
        self.enviados.append(evento)
        if indice in self.falhar_em:
            raise GatewayErro("x")


class InvocadorFalso:
    def __init__(self, falha=False):
        self.cargas, self.falha = [], falha

    def disparar(self, carga):
        if self.falha:
            raise InvocacaoErro("x")
        self.cargas.append(carga)


class FilaFalsa:
    def __init__(self, falha=False):
        self.comandos, self.falha = [], falha

    def enviar(self, comando):
        if self.falha:
            raise FilaErro("x")
        self.comandos.append(comando)


def montar(tokens=None, lwa=None, gateway=None, invocador=None, fila=None):
    contador = itertools.count(1)
    return Deps(
        config=Config(endpoint_id="pc-principal", mac=MAC),
        tokens=tokens or TokensFalso(),
        lwa=lwa or LwaFalso(),
        gateway=gateway or GatewayFalso(),
        invocador=invocador or InvocadorFalso(),
        fila=fila or FilaFalsa(),
        agora=lambda: AGORA,
        agora_iso=lambda: "2026-01-01T00:00:00.00Z",
        novo_id=lambda: f"id-{next(contador)}",
    )


def diretiva(namespace, nome, payload=None, endpoint="pc-principal"):
    corpo = {
        "directive": {
            "header": {"namespace": namespace, "name": nome, "payloadVersion": "3",
                       "messageId": "m", "correlationToken": "corr-1"},
            "payload": payload or {},
        }
    }
    if endpoint:
        corpo["directive"]["endpoint"] = {"endpointId": endpoint, "scope": {"type": "BearerToken", "token": TOKEN}}
    return corpo


def registro(expira_em=AGORA + 3600):
    return {"access_token": TOKEN, "refresh_token": REFRESH, "expira_em": int(expira_em)}


class Roteamento(unittest.TestCase):
    def test_discovery(self):
        r = processar(diretiva("Alexa.Discovery", "Discover", endpoint=None), montar())
        self.assertEqual(r["event"]["header"]["name"], "Discover.Response")

    def test_discovery_com_mac_configurado_errado_vira_erro_sem_vazar_o_valor(self):
        d = montar()
        d.config.mac = "mac-errado"
        with self.assertLogs(aplicacao.LOG, level="DEBUG") as capturado:
            r = processar(diretiva("Alexa.Discovery", "Discover", endpoint=None), d)
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")
        self.assertNotIn("mac-errado", "\n".join(capturado.output))

    def test_evento_invalido_vira_erro_sem_levantar(self):
        r = processar({"qualquer": "coisa"}, montar())
        self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_evento_que_nao_e_dict_nao_levanta(self):
        for ruim in (None, [], "texto", 42):
            with self.subTest(ruim=ruim):
                r = processar(ruim, montar())
                self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_turnon_sem_correlation_token(self):
        d = montar()
        evento = diretiva("Alexa.PowerController", "TurnOn")
        del evento["directive"]["header"]["correlationToken"]
        r = processar(evento, d)
        self.assertNotIn("correlationToken", r["event"]["header"])
        self.assertIsNone(d.invocador.cargas[0]["robot_interno"]["correlationToken"])

    def test_diretiva_desconhecida(self):
        r = processar(diretiva("Alexa.Outra", "Fazer"), montar())
        self.assertEqual(r["event"]["payload"]["type"], "INVALID_DIRECTIVE")

    def test_turnoff_poe_shutdown_na_fila_e_responde_off_na_hora(self):
        d = montar()
        r = processar(diretiva("Alexa.PowerController", "TurnOff"), d)
        self.assertEqual(d.fila.comandos, [{"versao": 1, "acao": "shutdown"}])
        self.assertEqual(r["event"]["header"]["name"], "Response")
        self.assertEqual(r["event"]["header"]["correlationToken"], "corr-1")
        self.assertEqual(r["event"]["endpoint"]["endpointId"], "pc-principal")
        self.assertEqual(r["context"]["properties"][0]["value"], "OFF")
        self.assertEqual(d.invocador.cargas, [])
        self.assertEqual(d.gateway.enviados, [])

    def test_turnoff_de_endpoint_desconhecido_nao_enfileira(self):
        d = montar()
        r = processar(diretiva("Alexa.PowerController", "TurnOff", endpoint="outro"), d)
        self.assertEqual(r["event"]["payload"]["type"], "NO_SUCH_ENDPOINT")
        self.assertEqual(d.fila.comandos, [])

    def test_turnoff_com_falha_na_fila_vira_erro(self):
        d = montar(fila=FilaFalsa(falha=True))
        r = processar(diretiva("Alexa.PowerController", "TurnOff"), d)
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")

    def test_turnon_nao_enfileira_nada(self):
        d = montar()
        processar(diretiva("Alexa.PowerController", "TurnOn"), d)
        self.assertEqual(d.fila.comandos, [])

    def test_carga_interna_nao_vale_dentro_de_diretiva_da_alexa(self):
        d = montar(tokens=TokensFalso(registro()))
        evento = diretiva("Alexa.Outra", "Fazer")
        evento["robot_interno"] = {"acao": "ligar", "endpointId": "pc-principal"}
        processar(evento, d)
        self.assertEqual(d.gateway.enviados, [])


class AcceptGrant(unittest.TestCase):
    def payload(self):
        return {"grant": {"type": "OAuth2.AuthorizationCode", "code": CODIGO}, "grantee": {"type": "BearerToken", "token": TOKEN}}

    def test_troca_o_codigo_e_guarda_os_tokens(self):
        d = montar()
        r = processar(diretiva("Alexa.Authorization", "AcceptGrant", self.payload(), endpoint=None), d)
        self.assertEqual(r["event"]["header"]["name"], "AcceptGrant.Response")
        self.assertEqual(d.lwa.chamadas, [("codigo", CODIGO)])
        self.assertEqual(d.tokens.registro, {"access_token": "novo-acesso", "refresh_token": "novo-refresh", "expira_em": int(AGORA) + 3600})

    def test_falhas_viram_accept_grant_failed(self):
        casos = {
            "lwa": montar(lwa=LwaFalso(falha=True)),
            "banco": montar(tokens=TokensFalso(falha=True)),
        }
        for nome, d in casos.items():
            with self.subTest(nome):
                r = processar(diretiva("Alexa.Authorization", "AcceptGrant", self.payload(), endpoint=None), d)
                self.assertEqual(r["event"]["payload"]["type"], "ACCEPT_GRANT_FAILED")

    def test_grant_sem_codigo(self):
        r = processar(diretiva("Alexa.Authorization", "AcceptGrant", {}, endpoint=None), montar())
        self.assertEqual(r["event"]["payload"]["type"], "ACCEPT_GRANT_FAILED")


class TurnOnSincrono(unittest.TestCase):
    def test_responde_deferred_e_dispara_a_invocacao_interna(self):
        d = montar()
        r = processar(diretiva("Alexa.PowerController", "TurnOn"), d)
        self.assertEqual(r["event"]["header"]["name"], "DeferredResponse")
        self.assertEqual(r["event"]["header"]["correlationToken"], "corr-1")
        self.assertEqual(
            d.invocador.cargas,
            [{"robot_interno": {"acao": "ligar", "endpointId": "pc-principal", "correlationToken": "corr-1"}}],
        )
        self.assertEqual(d.gateway.enviados, [], "nenhum evento pode sair antes da resposta síncrona")

    def test_endpoint_desconhecido(self):
        d = montar()
        r = processar(diretiva("Alexa.PowerController", "TurnOn", endpoint="outro"), d)
        self.assertEqual(r["event"]["payload"]["type"], "NO_SUCH_ENDPOINT")
        self.assertEqual(d.invocador.cargas, [])

    def test_falha_ao_agendar_vira_erro_interno(self):
        r = processar(diretiva("Alexa.PowerController", "TurnOn"), montar(invocador=InvocadorFalso(falha=True)))
        self.assertEqual(r["event"]["payload"]["type"], "INTERNAL_ERROR")


def carga_interna(**extra):
    base = {"acao": "ligar", "endpointId": "pc-principal", "correlationToken": "corr-1"}
    base.update(extra)
    return {"robot_interno": base}


class TurnOnAssincrono(unittest.TestCase):
    def test_envia_wakeup_e_depois_a_resposta_final(self):
        d = montar(tokens=TokensFalso(registro()))
        r = processar(carga_interna(), d)
        self.assertEqual(r, {"ok": True})
        nomes = [e["event"]["header"]["name"] for e in d.gateway.enviados]
        self.assertEqual(nomes, ["WakeUp", "Response"])
        for e in d.gateway.enviados:
            self.assertEqual(e["event"]["header"]["correlationToken"], "corr-1")
            self.assertEqual(e["event"]["endpoint"]["scope"]["token"], TOKEN)
        self.assertEqual(d.lwa.chamadas, [])

    def test_renova_token_perto_de_expirar_e_grava(self):
        d = montar(tokens=TokensFalso(registro(expira_em=AGORA + 10)))
        processar(carga_interna(), d)
        self.assertEqual(d.lwa.chamadas, [("refresh", REFRESH)])
        self.assertEqual(d.gateway.enviados[0]["event"]["endpoint"]["scope"]["token"], "renovado")
        self.assertEqual(d.tokens.registro["refresh_token"], "renovado-refresh")

    def test_margem_de_renovacao_exata(self):
        casos = {
            AGORA + aplicacao.MARGEM_RENOVACAO_S: True,
            AGORA + aplicacao.MARGEM_RENOVACAO_S + 1: False,
        }
        for expira_em, deve_renovar in casos.items():
            with self.subTest(expira_em=expira_em):
                d = montar(tokens=TokensFalso(registro(expira_em=expira_em)))
                processar(carga_interna(), d)
                self.assertEqual(bool(d.lwa.chamadas), deve_renovar)

    def test_renovacao_sem_novo_refresh_mantem_o_anterior(self):
        class LwaSemRefresh(LwaFalso):
            def renovar(self, refresh):
                self.chamadas.append(("refresh", refresh))
                return {"access_token": "renovado", "expires_in": 3600}

        d = montar(tokens=TokensFalso(registro(expira_em=AGORA)), lwa=LwaSemRefresh())
        processar(carga_interna(), d)
        self.assertEqual(d.tokens.registro["refresh_token"], REFRESH)
        self.assertEqual(d.tokens.registro["access_token"], "renovado")

    def test_sem_correlation_token_os_eventos_saem_sem_o_campo(self):
        d = montar(tokens=TokensFalso(registro()))
        processar({"robot_interno": {"acao": "ligar", "endpointId": "pc-principal", "correlationToken": None}}, d)
        for e in d.gateway.enviados:
            self.assertNotIn("correlationToken", e["event"]["header"])

    def test_falha_na_resposta_final_ainda_avisa_a_alexa(self):
        d = montar(tokens=TokensFalso(registro()), gateway=GatewayFalso(falhar_em={1}))
        self.assertEqual(processar(carga_interna(), d)["motivo"], "gateway")
        nomes = [e["event"]["header"]["name"] for e in d.gateway.enviados]
        self.assertEqual(nomes, ["WakeUp", "Response", "ErrorResponse"])

    def test_falha_ate_no_aviso_de_erro_nao_levanta(self):
        d = montar(tokens=TokensFalso(registro()), gateway=GatewayFalso(falhar_em={0, 1}))
        self.assertEqual(processar(carga_interna(), d)["motivo"], "gateway")
        self.assertEqual(len(d.gateway.enviados), 2)

    def test_sem_tokens_nao_envia_nada(self):
        d = montar(tokens=TokensFalso(None))
        self.assertEqual(processar(carga_interna(), d), {"ok": False, "motivo": "sem_token"})
        self.assertEqual(d.gateway.enviados, [])

    def test_falha_na_renovacao_nao_envia_nada(self):
        d = montar(tokens=TokensFalso(registro(expira_em=AGORA)), lwa=LwaFalso(falha=True))
        self.assertEqual(processar(carga_interna(), d)["motivo"], "sem_token")
        self.assertEqual(d.gateway.enviados, [])

    def test_falha_no_wakeup_tenta_avisar_a_alexa_do_erro_e_nao_manda_a_resposta_final(self):
        d = montar(tokens=TokensFalso(registro()), gateway=GatewayFalso(falhar_em={0}))
        self.assertEqual(processar(carga_interna(), d)["motivo"], "gateway")
        nomes = [e["event"]["header"]["name"] for e in d.gateway.enviados]
        self.assertEqual(nomes, ["WakeUp", "ErrorResponse"])

    def test_cargas_invalidas_sao_descartadas(self):
        for ruim in (carga_interna(acao="desligar"), carga_interna(endpointId="outro"), {"robot_interno": "x"}):
            with self.subTest(ruim=ruim):
                d = montar(tokens=TokensFalso(registro()))
                self.assertFalse(processar(ruim, d)["ok"])
                self.assertEqual(d.gateway.enviados, [])


class LogsSemSegredo(unittest.TestCase):
    def test_nenhum_log_carrega_token_codigo_ou_segredo(self):
        cenarios = [
            lambda: processar(diretiva("Alexa.PowerController", "TurnOn"), montar()),
            lambda: processar(carga_interna(), montar(tokens=TokensFalso(registro()))),
            lambda: processar(carga_interna(), montar(tokens=TokensFalso(registro()), gateway=GatewayFalso(falhar_em={0, 1}))),
            lambda: processar(carga_interna(), montar(tokens=TokensFalso(registro(AGORA)), lwa=LwaFalso(falha=True))),
            lambda: processar(
                diretiva("Alexa.Authorization", "AcceptGrant",
                         {"grant": {"type": "OAuth2.AuthorizationCode", "code": CODIGO}}, endpoint=None),
                montar(lwa=LwaFalso(falha=True)),
            ),
            lambda: processar({"directive": {"token": TOKEN}}, montar()),
        ]
        for cenario in cenarios:
            with self.assertLogs(aplicacao.LOG, level="DEBUG") as capturado:
                cenario()
            texto = "\n".join(capturado.output)
            for proibido in (TOKEN, REFRESH, CODIGO, SEGREDO_CLIENTE, "novo-acesso", "renovado"):
                self.assertNotIn(proibido, texto)


if __name__ == "__main__":
    unittest.main()
