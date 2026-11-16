"""Triggers the Lambda itself asynchronously, to send the TurnOn events after the response."""
from __future__ import annotations

import json
from typing import Any

from ..errors import InvocationError


class LambdaInvoker:
    def __init__(self, function_name: str, client: Any = None):
        if client is None:
            import boto3  # imported here so the tests do not need the SDK

            client = boto3.client("lambda")
        self._name = function_name
        self._client = client

    def trigger(self, payload: dict[str, Any]) -> None:
        try:
            self._client.invoke(
                FunctionName=self._name,
                InvocationType="Event",
                Payload=json.dumps(payload).encode("utf-8"),
            )
        except Exception:
            raise InvocationError("failed to trigger the asynchronous invocation") from None
