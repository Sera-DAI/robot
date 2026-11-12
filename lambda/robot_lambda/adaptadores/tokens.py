"""Tokens do AcceptGrant no DynamoDB. Skill pessoal: um único registro, o do dono."""
from __future__ import annotations

from typing import Any

from ..erros import ArmazenamentoErro

CHAVE = "dono"


class TokensDynamo:
    def __init__(self, nome_tabela: str, recurso: Any = None):
        if recurso is None:
            import boto3  # importado aqui para os testes não precisarem do SDK

            recurso = boto3.resource("dynamodb")
        self._tabela = recurso.Table(nome_tabela)

    def obter(self) -> dict[str, Any] | None:
        try:
            item = self._tabela.get_item(Key={"id": CHAVE}).get("Item")
            if not item:
                return None
            return {
                "access_token": item["access_token"],
                "refresh_token": item["refresh_token"],
                "expira_em": int(item["expira_em"]),  # o DynamoDB devolve Decimal
            }
        except Exception:
            raise ArmazenamentoErro("falha ao ler os tokens") from None

    def salvar(self, registro: dict[str, Any]) -> None:
        try:
            self._tabela.put_item(
                Item={
                    "id": CHAVE,
                    "access_token": registro["access_token"],
                    "refresh_token": registro["refresh_token"],
                    "expira_em": int(registro["expira_em"]),
                }
            )
        except Exception:
            raise ArmazenamentoErro("falha ao gravar os tokens") from None
