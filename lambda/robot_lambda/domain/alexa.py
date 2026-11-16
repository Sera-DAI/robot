"""Pure rules for the Alexa directives: routing, validation and building of responses.

No I/O. The clock and the identifiers come in as parameters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

VERSION = "3"
MAC_FORMAT = re.compile(r"^(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$")

ROUTE_DISCOVERY = "discovery"
ROUTE_ACCEPT_GRANT = "accept_grant"
ROUTE_TURN_ON = "turn_on"
ROUTE_TURN_OFF = "turn_off"
ROUTE_UNKNOWN = "unknown"

_ROUTES = {
    ("Alexa.Discovery", "Discover"): ROUTE_DISCOVERY,
    ("Alexa.Authorization", "AcceptGrant"): ROUTE_ACCEPT_GRANT,
    ("Alexa.PowerController", "TurnOn"): ROUTE_TURN_ON,
    ("Alexa.PowerController", "TurnOff"): ROUTE_TURN_OFF,
}

ERROR_NO_SUCH_ENDPOINT = "NO_SUCH_ENDPOINT"
ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_UNREACHABLE = "ENDPOINT_UNREACHABLE"
ERROR_INVALID_DIRECTIVE = "INVALID_DIRECTIVE"


@dataclass(frozen=True)
class Directive:
    namespace: str
    name: str
    correlation_token: str | None
    endpoint_id: str | None
    user_token: str | None
    payload: dict[str, Any]

    @property
    def route(self) -> str:
        return _ROUTES.get((self.namespace, self.name), ROUTE_UNKNOWN)


def parse(event: dict[str, Any]) -> Directive:
    """Reads the directive from the Alexa event. Raises ValueError if the format is not the expected one."""
    directive = event.get("directive") if isinstance(event, dict) else None
    if not isinstance(directive, dict):
        raise ValueError("event without a directive")
    header = directive.get("header")
    if not isinstance(header, dict):
        raise ValueError("directive without a header")
    if header.get("payloadVersion") != VERSION:
        raise ValueError("unsupported payload version")
    namespace, name = header.get("namespace"), header.get("name")
    if not isinstance(namespace, str) or not isinstance(name, str):
        raise ValueError("header without a namespace or a name")
    endpoint = directive.get("endpoint") if isinstance(directive.get("endpoint"), dict) else {}
    scope = endpoint.get("scope") if isinstance(endpoint.get("scope"), dict) else {}
    payload = directive.get("payload") if isinstance(directive.get("payload"), dict) else {}
    return Directive(
        namespace=namespace,
        name=name,
        correlation_token=header.get("correlationToken"),
        endpoint_id=endpoint.get("endpointId"),
        user_token=scope.get("token"),
        payload=payload,
    )


def validate_mac(mac: str) -> str:
    """Discovery requires the MAC with hyphens, as in the documentation example."""
    if not isinstance(mac, str) or not MAC_FORMAT.match(mac):
        raise ValueError("MAC outside the XX-XX-XX-XX-XX-XX format")
    return mac.upper()


def extract_grant_code(payload: dict[str, Any]) -> str:
    """Takes the authorization code from the AcceptGrant. Raises ValueError if it is missing."""
    grant = payload.get("grant")
    if not isinstance(grant, dict) or grant.get("type") != "OAuth2.AuthorizationCode":
        raise ValueError("invalid grant")
    code = grant.get("code")
    if not isinstance(code, str) or not code:
        raise ValueError("grant without a code")
    return code


def _header(namespace: str, name: str, msg_id: str, correlation_token: str | None = None) -> dict[str, str]:
    header = {
        "namespace": namespace,
        "name": name,
        "payloadVersion": VERSION,
        "messageId": msg_id,
    }
    if correlation_token:
        header["correlationToken"] = correlation_token
    return header


def _scope(token: str, endpoint_id: str) -> dict[str, Any]:
    return {"scope": {"type": "BearerToken", "token": token}, "endpointId": endpoint_id}


def _power_property(value: str, now_iso: str) -> dict[str, Any]:
    return {
        "namespace": "Alexa.PowerController",
        "name": "powerState",
        "value": value,
        "timeOfSample": now_iso,
        "uncertaintyInMilliseconds": 0,
    }


def discovery(endpoint_id: str, mac: str, msg_id: str) -> dict[str, Any]:
    """A single endpoint: the PC, with PowerController and WakeOnLANController."""
    mac = validate_mac(mac)
    capabilities = [
        {"type": "AlexaInterface", "interface": "Alexa", "version": VERSION},
        {
            "type": "AlexaInterface",
            "interface": "Alexa.PowerController",
            "version": VERSION,
            "properties": {
                "supported": [{"name": "powerState"}],
                "proactivelyReported": False,
                "retrievable": False,
            },
        },
        {
            "type": "AlexaInterface",
            "interface": "Alexa.WakeOnLANController",
            "version": VERSION,
            "properties": {},
            "configuration": {"MACAddresses": [mac]},
        },
    ]
    return {
        "event": {
            "header": _header("Alexa.Discovery", "Discover.Response", msg_id),
            "payload": {
                "endpoints": [
                    {
                        "endpointId": endpoint_id,
                        "manufacturerName": "Robot",
                        "friendlyName": "PC",
                        "description": "PC controlled by voice",
                        "displayCategories": ["COMPUTER"],
                        "capabilities": capabilities,
                    }
                ]
            },
        }
    }


def accept_grant_ok(msg_id: str) -> dict[str, Any]:
    return {"event": {"header": _header("Alexa.Authorization", "AcceptGrant.Response", msg_id), "payload": {}}}


def accept_grant_error(msg_id: str) -> dict[str, Any]:
    return {
        "event": {
            "header": _header("Alexa.Authorization", "ErrorResponse", msg_id),
            "payload": {"type": "ACCEPT_GRANT_FAILED", "message": "Failed to authorize sending events"},
        }
    }


def deferred(correlation_token: str | None, msg_id: str, seconds: int = 15) -> dict[str, Any]:
    """Synchronous response of TurnOn: the rest follows through asynchronous events."""
    return {
        "event": {
            "header": _header("Alexa", "DeferredResponse", msg_id, correlation_token),
            "payload": {"estimatedDeferralInSeconds": seconds},
        }
    }


def wakeup_event(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, now_iso: str) -> dict[str, Any]:
    """Asks Alexa to make the Echo broadcast the Wake-on-LAN. The power state in the context is OFF."""
    return {
        "context": {"properties": [_power_property("OFF", now_iso)]},
        "event": {
            "header": _header("Alexa.WakeOnLANController", "WakeUp", msg_id, correlation_token),
            "endpoint": _scope(token, endpoint_id),
            "payload": {},
        },
    }


def response_event(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, now_iso: str) -> dict[str, Any]:
    """Final response of TurnOn, with powerState ON."""
    return {
        "context": {"properties": [_power_property("ON", now_iso)]},
        "event": {
            "header": _header("Alexa", "Response", msg_id, correlation_token),
            "endpoint": _scope(token, endpoint_id),
            "payload": {},
        },
    }


def sync_response(
    endpoint_id: str, token: str | None, correlation_token: str | None, msg_id: str, state: str, now_iso: str,
) -> dict[str, Any]:
    """Response returned right away, as the Lambda's return value, with the given powerState."""
    endpoint: dict[str, Any] = {"endpointId": endpoint_id}
    if token:
        endpoint["scope"] = {"type": "BearerToken", "token": token}
    return {
        "context": {"properties": [_power_property(state, now_iso)]},
        "event": {
            "header": _header("Alexa", "Response", msg_id, correlation_token),
            "endpoint": endpoint,
            "payload": {},
        },
    }


def error_event(token: str, endpoint_id: str, correlation_token: str | None, msg_id: str, kind: str, message: str) -> dict[str, Any]:
    """ErrorResponse sent as an asynchronous event."""
    return {
        "event": {
            "header": _header("Alexa", "ErrorResponse", msg_id, correlation_token),
            "endpoint": _scope(token, endpoint_id),
            "payload": {"type": kind, "message": message},
        }
    }


def sync_error(endpoint_id: str | None, correlation_token: str | None, msg_id: str, kind: str, message: str) -> dict[str, Any]:
    """ErrorResponse returned right away, as the Lambda's return value."""
    response: dict[str, Any] = {
        "event": {
            "header": _header("Alexa", "ErrorResponse", msg_id, correlation_token),
            "payload": {"type": kind, "message": message},
        }
    }
    if endpoint_id:
        response["event"]["endpoint"] = {"endpointId": endpoint_id}
    return response
