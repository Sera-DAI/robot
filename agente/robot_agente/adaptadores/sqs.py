"""Cliente mínimo da fila SQS (protocolo JSON), só com receber e apagar.

Nunca registra credencial, cabeçalho de autorização nem corpo de resposta.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ..erros import FilaErro
from . import sigv4

# A URL da fila só pode apontar para o SQS da AWS: a assinatura nunca segue para outro endereço.
FORMATO_URL = re.compile(r"^https://sqs\.([a-z]{2}(?:-[a-z]+)+-\d)\.amazonaws\.com/\d{12}/[A-Za-z0-9_-]{1,80}$")
ESPERA_S = 20  # long polling: uma chamada a cada 20 s com a fila vazia


@dataclass(frozen=True)
class Mensagem:
    corpo: str
    recibo: str
    enviada_em_ms: int | None


def regiao_da_url(url: str) -> str:
    achado = FORMATO_URL.match(url) if isinstance(url, str) else None
    if not achado:
        raise FilaErro("URL da fila fora do formato esperado")
    return achado.group(1)


def _agora_amz() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class ClienteSqs:
    def __init__(self, url: str, id_chave: str, segredo: str, agora_amz: Callable[[], str] = _agora_amz):
        self._regiao = regiao_da_url(url)
        self._url = url
        self._host = f"sqs.{self._regiao}.amazonaws.com"
        self._id_chave = id_chave
        self._segredo = segredo
        self._agora_amz = agora_amz

    def receber(self) -> list[Mensagem]:
        dados = self._chamar(
            "ReceiveMessage",
            {
                "QueueUrl": self._url,
                "MaxNumberOfMessages": 10,
                "WaitTimeSeconds": ESPERA_S,
                "MessageSystemAttributeNames": ["SentTimestamp"],
            },
            limite_s=ESPERA_S + 15,
        )
        mensagens = []
        for bruta in dados.get("Messages") or []:
            if not isinstance(bruta, dict) or not isinstance(bruta.get("ReceiptHandle"), str):
                continue
            atributos = bruta.get("Attributes") if isinstance(bruta.get("Attributes"), dict) else {}
            enviada = atributos.get("SentTimestamp")
            mensagens.append(
                Mensagem(
                    corpo=bruta.get("Body") if isinstance(bruta.get("Body"), str) else "",
                    recibo=bruta["ReceiptHandle"],
                    enviada_em_ms=int(enviada) if isinstance(enviada, str) and enviada.isdigit() else None,
                )
            )
        return mensagens

    def apagar(self, recibo: str) -> None:
        self._chamar("DeleteMessage", {"QueueUrl": self._url, "ReceiptHandle": recibo}, limite_s=15)

    def _chamar(self, operacao: str, carga: dict[str, Any], limite_s: int) -> dict[str, Any]:
        corpo = json.dumps(carga).encode("utf-8")
        cabecalhos = sigv4.assinar_post(
            host=self._host, caminho="/", corpo=corpo,
            cabecalhos={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": f"AmazonSQS.{operacao}"},
            id_chave=self._id_chave, segredo=self._segredo,
            regiao=self._regiao, servico="sqs", instante=self._agora_amz(),
        )
        cabecalhos.pop("host")  # o urllib define o Host a partir da URL
        pedido = urllib.request.Request(f"https://{self._host}/", data=corpo, headers=cabecalhos, method="POST")
        try:
            with urllib.request.urlopen(pedido, timeout=limite_s) as resposta:
                texto = resposta.read()
            dados = json.loads(texto) if texto.strip() else {}
        except urllib.error.HTTPError as erro:
            # Só o status: o corpo do erro pode repetir dados do pedido.
            raise FilaErro(f"a fila respondeu {operacao} com HTTP {erro.code}") from None
        except Exception:
            raise FilaErro(f"falha de rede ou de formato em {operacao}") from None
        if not isinstance(dados, dict):
            raise FilaErro(f"resposta inesperada em {operacao}")
        return dados
