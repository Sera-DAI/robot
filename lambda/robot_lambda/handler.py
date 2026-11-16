"""Lambda entry point. It only builds the dependencies from the environment and delegates."""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .adapters.gateway import GatewayClient
from .adapters.invoker import LambdaInvoker
from .adapters.lwa import LwaClient
from .adapters.queue import SqsQueue
from .adapters.tokens import DynamoTokens
from .application import Config, Deps, process

logging.getLogger().setLevel(logging.INFO)

_deps: Deps | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.00Z")


def _build() -> Deps:
    return Deps(
        config=Config(
            endpoint_id=os.environ.get("ROBOT_ENDPOINT_ID", "pc-principal"),
            mac=os.environ["ROBOT_MAC"],
        ),
        tokens=DynamoTokens(os.environ["TOKENS_TABLE"]),
        lwa=LwaClient(os.environ["LWA_CLIENT_ID"], os.environ["LWA_CLIENT_SECRET"]),
        gateway=GatewayClient(),  # fixed URL: the Bearer token never goes to an address from the environment
        invoker=LambdaInvoker(os.environ["AWS_LAMBDA_FUNCTION_NAME"]),
        queue=SqsQueue(os.environ["QUEUE_URL"]),
        now=time.time,
        now_iso=_now_iso,
        new_id=lambda: str(uuid.uuid4()),
    )


def handle(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global _deps
    if _deps is None:
        _deps = _build()
    return process(event, _deps)
