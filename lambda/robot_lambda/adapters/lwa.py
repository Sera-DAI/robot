"""Login with Amazon: exchange of the AcceptGrant code and token renewal.

Never logs a response body, token or secret; error messages carry only the status.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..errors import LwaError

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
TIMEOUT_S = 5


class LwaClient:
    def __init__(self, client_id: str, client_secret: str, url: str = TOKEN_URL):
        self._client_id = client_id
        self._client_secret = client_secret
        self._url = url

    def exchange_code(self, code: str) -> dict[str, Any]:
        return self._request({"grant_type": "authorization_code", "code": code})

    def renew(self, refresh_token: str) -> dict[str, Any]:
        return self._request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def _request(self, fields: dict[str, str]) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {**fields, "client_id": self._client_id, "client_secret": self._client_secret}
        ).encode("ascii")
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise LwaError(f"LWA answered with status {error.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise LwaError("network failure or unreadable response from LWA") from None
        for field in ("access_token", "refresh_token", "expires_in"):
            if field not in data:
                raise LwaError("LWA response without the expected fields")
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_in": int(data["expires_in"]),
        }
