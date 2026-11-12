"""Login with Amazon: troca do código do AcceptGrant e renovação do token.

Não registra corpo de resposta, token nem segredo; as mensagens de erro só levam o status.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..erros import LwaErro

URL_TOKEN = "https://api.amazon.com/auth/o2/token"
TEMPO_LIMITE_S = 5


class ClienteLwa:
    def __init__(self, client_id: str, client_secret: str, url: str = URL_TOKEN):
        self._client_id = client_id
        self._client_secret = client_secret
        self._url = url

    def trocar_codigo(self, codigo: str) -> dict[str, Any]:
        return self._pedir({"grant_type": "authorization_code", "code": codigo})

    def renovar(self, refresh_token: str) -> dict[str, Any]:
        return self._pedir({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def _pedir(self, campos: dict[str, str]) -> dict[str, Any]:
        corpo = urllib.parse.urlencode(
            {**campos, "client_id": self._client_id, "client_secret": self._client_secret}
        ).encode("ascii")
        pedido = urllib.request.Request(
            self._url,
            data=corpo,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:  # noqa: S310
                dados = json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            raise LwaErro(f"LWA respondeu status {erro.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise LwaErro("falha de rede ou resposta ilegível do LWA") from None
        for campo in ("access_token", "refresh_token", "expires_in"):
            if campo not in dados:
                raise LwaErro("resposta do LWA sem os campos esperados")
        return {
            "access_token": dados["access_token"],
            "refresh_token": dados["refresh_token"],
            "expires_in": int(dados["expires_in"]),
        }
