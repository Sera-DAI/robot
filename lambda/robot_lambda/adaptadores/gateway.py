"""Gateway de eventos da Alexa. A região do endpoint é a da Lambda (us-east-1: América do Norte)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..erros import GatewayErro

URL_GATEWAY = "https://api.amazonalexa.com/v3/events"
TEMPO_LIMITE_S = 5


class ClienteGateway:
    def __init__(self, url: str = URL_GATEWAY):
        self._url = url

    def enviar(self, evento: dict[str, Any]) -> None:
        pedido = urllib.request.Request(
            self._url,
            data=json.dumps(evento).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:  # noqa: S310
                if resposta.status >= 300:
                    raise GatewayErro(f"gateway respondeu status {resposta.status}")
        except urllib.error.HTTPError as erro:
            raise GatewayErro(f"gateway respondeu status {erro.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise GatewayErro("falha de rede ao falar com o gateway") from None
