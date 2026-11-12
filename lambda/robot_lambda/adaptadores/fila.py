"""Fila SQS de comandos para o agente do PC. Só envia; quem consome é o agente."""
from __future__ import annotations

import json
from typing import Any

from ..erros import FilaErro


class FilaSqs:
    def __init__(self, url: str, cliente: Any = None):
        if cliente is None:
            import boto3  # importado aqui para os testes não precisarem do SDK

            cliente = boto3.client("sqs")
        self._url = url
        self._cliente = cliente

    def enviar(self, comando: dict[str, Any]) -> None:
        try:
            self._cliente.send_message(QueueUrl=self._url, MessageBody=json.dumps(comando))
        except Exception:
            raise FilaErro("falha ao enviar o comando para a fila") from None
