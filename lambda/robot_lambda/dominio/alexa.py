"""Regras puras das diretivas da Alexa: roteamento, validação e montagem de respostas.

Sem I/O. Relógio e identificadores entram por parâmetro.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

VERSAO = "3"
FORMATO_MAC = re.compile(r"^(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$")

ROTA_DISCOVERY = "discovery"
ROTA_ACCEPT_GRANT = "accept_grant"
ROTA_LIGAR = "ligar"
ROTA_DESLIGAR = "desligar"
ROTA_DESCONHECIDA = "desconhecida"

_ROTAS = {
    ("Alexa.Discovery", "Discover"): ROTA_DISCOVERY,
    ("Alexa.Authorization", "AcceptGrant"): ROTA_ACCEPT_GRANT,
    ("Alexa.PowerController", "TurnOn"): ROTA_LIGAR,
    ("Alexa.PowerController", "TurnOff"): ROTA_DESLIGAR,
}

ERRO_ENDPOINT_INEXISTENTE = "NO_SUCH_ENDPOINT"
ERRO_INTERNO = "INTERNAL_ERROR"
ERRO_INACESSIVEL = "ENDPOINT_UNREACHABLE"
ERRO_DIRETIVA_INVALIDA = "INVALID_DIRECTIVE"


@dataclass(frozen=True)
class Diretiva:
    namespace: str
    nome: str
    correlation_token: str | None
    endpoint_id: str | None
    token_usuario: str | None
    payload: dict[str, Any]

    @property
    def rota(self) -> str:
        return _ROTAS.get((self.namespace, self.nome), ROTA_DESCONHECIDA)


def separar(evento: dict[str, Any]) -> Diretiva:
    """Lê a diretiva do evento da Alexa. Levanta ValueError se o formato não for o esperado."""
    diretiva = evento.get("directive") if isinstance(evento, dict) else None
    if not isinstance(diretiva, dict):
        raise ValueError("evento sem diretiva")
    cabecalho = diretiva.get("header")
    if not isinstance(cabecalho, dict):
        raise ValueError("diretiva sem cabeçalho")
    if cabecalho.get("payloadVersion") != VERSAO:
        raise ValueError("versão de payload não suportada")
    namespace, nome = cabecalho.get("namespace"), cabecalho.get("name")
    if not isinstance(namespace, str) or not isinstance(nome, str):
        raise ValueError("cabeçalho sem namespace ou nome")
    endpoint = diretiva.get("endpoint") if isinstance(diretiva.get("endpoint"), dict) else {}
    escopo = endpoint.get("scope") if isinstance(endpoint.get("scope"), dict) else {}
    payload = diretiva.get("payload") if isinstance(diretiva.get("payload"), dict) else {}
    return Diretiva(
        namespace=namespace,
        nome=nome,
        correlation_token=cabecalho.get("correlationToken"),
        endpoint_id=endpoint.get("endpointId"),
        token_usuario=escopo.get("token"),
        payload=payload,
    )


def validar_mac(mac: str) -> str:
    """O Discovery exige o MAC com hífens, como no exemplo da documentação."""
    if not isinstance(mac, str) or not FORMATO_MAC.match(mac):
        raise ValueError("MAC fora do formato XX-XX-XX-XX-XX-XX")
    return mac.upper()


def extrair_codigo_grant(payload: dict[str, Any]) -> str:
    """Pega o código de autorização do AcceptGrant. Levanta ValueError se faltar."""
    grant = payload.get("grant")
    if not isinstance(grant, dict) or grant.get("type") != "OAuth2.AuthorizationCode":
        raise ValueError("grant inválido")
    codigo = grant.get("code")
    if not isinstance(codigo, str) or not codigo:
        raise ValueError("grant sem código")
    return codigo


def _cabecalho(namespace: str, nome: str, msg_id: str, correlation_token: str | None = None) -> dict[str, str]:
    cabecalho = {
        "namespace": namespace,
        "name": nome,
        "payloadVersion": VERSAO,
        "messageId": msg_id,
    }
    if correlation_token:
        cabecalho["correlationToken"] = correlation_token
    return cabecalho


def _escopo(token: str, endpoint_id: str) -> dict[str, Any]:
    return {"scope": {"type": "BearerToken", "token": token}, "endpointId": endpoint_id}


def _propriedade_energia(valor: str, agora_iso: str) -> dict[str, Any]:
    return {
        "namespace": "Alexa.PowerController",
        "name": "powerState",
        "value": valor,
        "timeOfSample": agora_iso,
        "uncertaintyInMilliseconds": 0,
    }


def discovery(endpoint_id: str, mac: str, msg_id: str) -> dict[str, Any]:
    """Um único endpoint: o PC, com PowerController e WakeOnLANController."""
    mac = validar_mac(mac)
    capacidades = [
        {"type": "AlexaInterface", "interface": "Alexa", "version": VERSAO},
        {
            "type": "AlexaInterface",
            "interface": "Alexa.PowerController",
            "version": VERSAO,
            "properties": {
                "supported": [{"name": "powerState"}],
                "proactivelyReported": False,
                "retrievable": False,
            },
        },
        {
            "type": "AlexaInterface",
            "interface": "Alexa.WakeOnLANController",
            "version": VERSAO,
            "properties": {},
            "configuration": {"MACAddresses": [mac]},
        },
    ]
    return {
        "event": {
            "header": _cabecalho("Alexa.Discovery", "Discover.Response", msg_id),
            "payload": {
                "endpoints": [
                    {
                        "endpointId": endpoint_id,
                        "manufacturerName": "Robot",
                        "friendlyName": "PC",
                        "description": "PC controlado por voz",
                        "displayCategories": ["COMPUTER"],
                        "capabilities": capacidades,
                    }
                ]
            },
        }
    }


def accept_grant_ok(msg_id: str) -> dict[str, Any]:
    return {"event": {"header": _cabecalho("Alexa.Authorization", "AcceptGrant.Response", msg_id), "payload": {}}}


def accept_grant_erro(msg_id: str) -> dict[str, Any]:
    return {
        "event": {
            "header": _cabecalho("Alexa.Authorization", "ErrorResponse", msg_id),
            "payload": {"type": "ACCEPT_GRANT_FAILED", "message": "Falha ao autorizar o envio de eventos"},
        }
    }


def deferred(correlation_token: str | None, msg_id: str, segundos: int = 15) -> dict[str, Any]:
    """Resposta síncrona do TurnOn: o resto segue por eventos assíncronos."""
    return {
        "event": {
            "header": _cabecalho("Alexa", "DeferredResponse", msg_id, correlation_token),
            "payload": {"estimatedDeferralInSeconds": segundos},
        }
    }


def evento_wakeup(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, agora_iso: str) -> dict[str, Any]:
    """Pede à Alexa que o Echo transmita o Wake-on-LAN. O estado de energia do contexto é OFF."""
    return {
        "context": {"properties": [_propriedade_energia("OFF", agora_iso)]},
        "event": {
            "header": _cabecalho("Alexa.WakeOnLANController", "WakeUp", msg_id, correlation_token),
            "endpoint": _escopo(token, endpoint_id),
            "payload": {},
        },
    }


def evento_resposta(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, agora_iso: str) -> dict[str, Any]:
    """Resposta final do TurnOn, com powerState em ON."""
    return {
        "context": {"properties": [_propriedade_energia("ON", agora_iso)]},
        "event": {
            "header": _cabecalho("Alexa", "Response", msg_id, correlation_token),
            "endpoint": _escopo(token, endpoint_id),
            "payload": {},
        },
    }


def resposta_sincrona(
    endpoint_id: str, token: str | None, correlation_token: str | None, msg_id: str, estado: str, agora_iso: str,
) -> dict[str, Any]:
    """Response devolvida na hora, como retorno da Lambda, com o powerState informado."""
    endpoint: dict[str, Any] = {"endpointId": endpoint_id}
    if token:
        endpoint["scope"] = {"type": "BearerToken", "token": token}
    return {
        "context": {"properties": [_propriedade_energia(estado, agora_iso)]},
        "event": {
            "header": _cabecalho("Alexa", "Response", msg_id, correlation_token),
            "endpoint": endpoint,
            "payload": {},
        },
    }


def evento_erro(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, tipo: str, mensagem: str) -> dict[str, Any]:
    """ErrorResponse enviado como evento assíncrono."""
    return {
        "event": {
            "header": _cabecalho("Alexa", "ErrorResponse", msg_id, correlation_token),
            "endpoint": _escopo(token, endpoint_id),
            "payload": {"type": tipo, "message": mensagem},
        }
    }


def erro_sincrono(endpoint_id: str | None, correlation_token: str | None, msg_id: str, tipo: str, mensagem: str) -> dict[str, Any]:
    """ErrorResponse devolvido na hora, como retorno da Lambda."""
    resposta: dict[str, Any] = {
        "event": {
            "header": _cabecalho("Alexa", "ErrorResponse", msg_id, correlation_token),
            "payload": {"type": tipo, "message": mensagem},
        }
    }
    if endpoint_id:
        resposta["event"]["endpoint"] = {"endpointId": endpoint_id}
    return resposta
