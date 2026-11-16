"""Alexa event gateway. The endpoint region is the Lambda's (us-east-1: North America)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..errors import GatewayError

GATEWAY_URL = "https://api.amazonalexa.com/v3/events"
TIMEOUT_S = 5


class GatewayClient:
    def __init__(self, url: str = GATEWAY_URL):
        self._url = url

    def send(self, event: dict[str, Any]) -> None:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(event).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                if response.status >= 300:
                    raise GatewayError(f"gateway answered with status {response.status}")
        except urllib.error.HTTPError as error:
            raise GatewayError(f"gateway answered with status {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise GatewayError("network failure talking to the gateway") from None
