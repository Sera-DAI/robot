"""Dispara a própria Lambda de forma assíncrona para enviar os eventos do TurnOn depois da resposta."""
from __future__ import annotations

import json
from typing import Any

from ..erros import InvocacaoErro


class InvocadorLambda:
    def __init__(self, nome_funcao: str, cliente: Any = None):
        if cliente is None:
            import boto3  # importado aqui para os testes não precisarem do SDK

            cliente = boto3.client("lambda")
        self._nome = nome_funcao
        self._cliente = cliente

    def disparar(self, carga: dict[str, Any]) -> None:
        try:
            self._cliente.invoke(
                FunctionName=self._nome,
                InvocationType="Event",
                Payload=json.dumps(carga).encode("utf-8"),
            )
        except Exception:
            raise InvocacaoErro("falha ao disparar a invocação assíncrona") from None
