"""Ponto de entrada da Lambda. Só monta as dependências a partir do ambiente e delega."""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .adaptadores.fila import FilaSqs
from .adaptadores.gateway import ClienteGateway
from .adaptadores.invocador import InvocadorLambda
from .adaptadores.lwa import ClienteLwa
from .adaptadores.tokens import TokensDynamo
from .aplicacao import Config, Deps, processar

logging.getLogger().setLevel(logging.INFO)

_deps: Deps | None = None


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.00Z")


def _montar() -> Deps:
    return Deps(
        config=Config(
            endpoint_id=os.environ.get("ROBOT_ENDPOINT_ID", "pc-principal"),
            mac=os.environ["ROBOT_MAC"],
        ),
        tokens=TokensDynamo(os.environ["TABELA_TOKENS"]),
        lwa=ClienteLwa(os.environ["LWA_CLIENT_ID"], os.environ["LWA_CLIENT_SECRET"]),
        gateway=ClienteGateway(),  # URL fixa: o token Bearer nunca segue para endereço vindo do ambiente
        invocador=InvocadorLambda(os.environ["AWS_LAMBDA_FUNCTION_NAME"]),
        fila=FilaSqs(os.environ["FILA_URL"]),
        agora=time.time,
        agora_iso=_agora_iso,
        novo_id=lambda: str(uuid.uuid4()),
    )


def lidar(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    global _deps
    if _deps is None:
        _deps = _montar()
    return processar(evento, _deps)
