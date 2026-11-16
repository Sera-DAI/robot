"""Application: wires the domain rules to the adapters. Thin, with no business rules of its own."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .domain import alexa, commands
from .errors import (
    GatewayError,
    InvocationError,
    LwaError,
    QueueError,
    StorageError,
)

LOG = logging.getLogger(__name__)

RENEWAL_MARGIN_S = 60
INTERNAL_KEY = "robot_internal"


class Tokens(Protocol):
    def get(self) -> dict[str, Any] | None: ...
    def save(self, record: dict[str, Any]) -> None: ...


class Lwa(Protocol):
    def exchange_code(self, code: str) -> dict[str, Any]: ...
    def renew(self, refresh_token: str) -> dict[str, Any]: ...


class Gateway(Protocol):
    def send(self, event: dict[str, Any]) -> None: ...


class Invoker(Protocol):
    def trigger(self, payload: dict[str, Any]) -> None: ...


class Queue(Protocol):
    def send(self, command: dict[str, Any]) -> None: ...


@dataclass
class Config:
    endpoint_id: str
    mac: str


@dataclass
class Deps:
    config: Config
    tokens: Tokens
    lwa: Lwa
    gateway: Gateway
    invoker: Invoker
    queue: Queue
    now: Callable[[], float]  # seconds since the epoch
    now_iso: Callable[[], str]
    new_id: Callable[[], str]


def process(event: dict[str, Any], d: Deps) -> dict[str, Any]:
    """Entry point. Only the route log is recorded: never the event, which carries a token."""
    if isinstance(event, dict) and "directive" not in event and INTERNAL_KEY in event:
        return _process_internal(event[INTERNAL_KEY], d)
    try:
        directive = alexa.parse(event)
    except ValueError:
        LOG.warning("event discarded: invalid format")
        return alexa.sync_error(None, None, d.new_id(), alexa.ERROR_INVALID_DIRECTIVE, "Invalid directive")

    LOG.info("directive received: %s", directive.route)
    if directive.route == alexa.ROUTE_DISCOVERY:
        try:
            return alexa.discovery(d.config.endpoint_id, d.config.mac, d.new_id())
        except ValueError:
            LOG.error("Discovery failed: configured MAC is outside the expected format")
            return alexa.sync_error(None, None, d.new_id(), alexa.ERROR_INTERNAL, "Invalid configuration")
    if directive.route == alexa.ROUTE_ACCEPT_GRANT:
        return _accept_grant(directive, d)
    if directive.route == alexa.ROUTE_TURN_ON:
        return _turn_on(directive, d)
    if directive.route == alexa.ROUTE_TURN_OFF:
        return _turn_off(directive, d)
    return alexa.sync_error(
        directive.endpoint_id, directive.correlation_token, d.new_id(),
        alexa.ERROR_INVALID_DIRECTIVE, "Unsupported directive",
    )


def _accept_grant(directive: alexa.Directive, d: Deps) -> dict[str, Any]:
    try:
        code = alexa.extract_grant_code(directive.payload)
        data = d.lwa.exchange_code(code)
        d.tokens.save(_record(data, d.now()))
    except (ValueError, LwaError, StorageError) as error:
        LOG.error("AcceptGrant failed: %s", type(error).__name__)
        return alexa.accept_grant_error(d.new_id())
    return alexa.accept_grant_ok(d.new_id())


def _turn_on(directive: alexa.Directive, d: Deps) -> dict[str, Any]:
    if directive.endpoint_id != d.config.endpoint_id:
        return alexa.sync_error(
            directive.endpoint_id, directive.correlation_token, d.new_id(),
            alexa.ERROR_NO_SUCH_ENDPOINT, "Unknown device",
        )
    try:
        d.invoker.trigger(
            {
                INTERNAL_KEY: {
                    "action": "turn_on",
                    "endpointId": directive.endpoint_id,
                    "correlationToken": directive.correlation_token,
                }
            }
        )
    except InvocationError as error:
        LOG.error("TurnOn failed to schedule the events: %s", type(error).__name__)
        return alexa.sync_error(
            directive.endpoint_id, directive.correlation_token, d.new_id(),
            alexa.ERROR_INTERNAL, "Failed to start the command",
        )
    return alexa.deferred(directive.correlation_token, d.new_id())


def _turn_off(directive: alexa.Directive, d: Deps) -> dict[str, Any]:
    """Puts the command on the queue and answers right away. The PC agent is the one that shuts down."""
    if directive.endpoint_id != d.config.endpoint_id:
        return alexa.sync_error(
            directive.endpoint_id, directive.correlation_token, d.new_id(),
            alexa.ERROR_NO_SUCH_ENDPOINT, "Unknown device",
        )
    try:
        d.queue.send(commands.build(commands.ACTION_SHUTDOWN))
    except QueueError as error:
        LOG.error("TurnOff failed to send the command to the queue: %s", type(error).__name__)
        return alexa.sync_error(
            directive.endpoint_id, directive.correlation_token, d.new_id(),
            alexa.ERROR_INTERNAL, "Failed to send the command",
        )
    LOG.info("TurnOff: shutdown command sent to the queue")
    return alexa.sync_response(
        directive.endpoint_id, directive.user_token, directive.correlation_token,
        d.new_id(), "OFF", d.now_iso(),
    )


def _process_internal(payload: Any, d: Deps) -> dict[str, Any]:
    """Second, asynchronous invocation: sends WakeUp and the final Response to the gateway."""
    if not isinstance(payload, dict) or payload.get("action") != "turn_on":
        LOG.warning("internal invocation discarded: unknown action")
        return {"ok": False, "reason": "unknown_action"}
    endpoint_id = payload.get("endpointId")
    correlation = payload.get("correlationToken")
    if endpoint_id != d.config.endpoint_id:
        LOG.warning("internal invocation discarded: unknown endpoint")
        return {"ok": False, "reason": "unknown_endpoint"}

    try:
        token = _valid_token(d)
    except (LwaError, StorageError) as error:
        LOG.error("no token to send events: %s", type(error).__name__)
        return {"ok": False, "reason": "no_token"}
    if token is None:
        LOG.error("no token to send events: AcceptGrant not completed yet")
        return {"ok": False, "reason": "no_token"}

    try:
        d.gateway.send(alexa.wakeup_event(token, endpoint_id, correlation, d.new_id(), d.now_iso()))
        d.gateway.send(alexa.response_event(token, endpoint_id, correlation, d.new_id(), d.now_iso()))
    except GatewayError as error:
        LOG.error("sending events failed: %s", type(error).__name__)
        _try_send_error(token, endpoint_id, correlation, d)
        return {"ok": False, "reason": "gateway"}
    LOG.info("TurnOn: WakeUp and Response sent to the gateway")
    return {"ok": True}


def _try_send_error(token: str, endpoint_id: str, correlation: str | None, d: Deps) -> None:
    try:
        d.gateway.send(
            alexa.error_event(token, endpoint_id, correlation, d.new_id(), alexa.ERROR_INTERNAL, "Failed to turn the PC on")
        )
    except GatewayError:
        LOG.error("could not tell Alexa about the error")


def _valid_token(d: Deps) -> str | None:
    record = d.tokens.get()
    if record is None:
        return None
    if record["expires_at"] - d.now() > RENEWAL_MARGIN_S:
        return record["access_token"]
    renewed = d.lwa.renew(record["refresh_token"])
    d.tokens.save(_record(renewed, d.now(), previous_refresh=record["refresh_token"]))
    return renewed["access_token"]


def _record(data: dict[str, Any], now: float, previous_refresh: str | None = None) -> dict[str, Any]:
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or previous_refresh,
        "expires_at": int(now) + int(data["expires_in"]),
    }
