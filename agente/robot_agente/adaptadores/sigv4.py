"""Assinatura AWS Signature Version 4 só com a biblioteca padrão.

O agente roda com privilégio para desligar o PC; por isso não depende de pacote de terceiros.
Nada aqui registra ou devolve o segredo.
"""
from __future__ import annotations

import hashlib
import hmac

ALGORITMO = "AWS4-HMAC-SHA256"


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).digest()


def chave_de_assinatura(segredo: str, data: str, regiao: str, servico: str) -> bytes:
    chave = _hmac(("AWS4" + segredo).encode("utf-8"), data)
    for parte in (regiao, servico, "aws4_request"):
        chave = _hmac(chave, parte)
    return chave


def assinar_post(
    *, host: str, caminho: str, cabecalhos: dict[str, str], corpo: bytes,
    id_chave: str, segredo: str, regiao: str, servico: str, instante: str,
) -> dict[str, str]:
    """Devolve os cabeçalhos do POST já com Authorization.

    `instante` vem no formato AAAAMMDDTHHMMSSZ (UTC). Sem query string: o SQS usa corpo JSON.
    """
    data = instante[:8]
    todos = {k.lower(): " ".join(v.split()) for k, v in cabecalhos.items()}
    todos["host"] = host
    todos["x-amz-date"] = instante
    nomes = sorted(todos)
    canonicos = "".join(f"{nome}:{todos[nome]}\n" for nome in nomes)
    assinados = ";".join(nomes)
    pedido = "\n".join(["POST", caminho, "", canonicos, assinados, hashlib.sha256(corpo).hexdigest()])
    escopo = f"{data}/{regiao}/{servico}/aws4_request"
    a_assinar = "\n".join([ALGORITMO, instante, escopo, hashlib.sha256(pedido.encode("utf-8")).hexdigest()])
    assinatura = hmac.new(
        chave_de_assinatura(segredo, data, regiao, servico), a_assinar.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    todos["authorization"] = (
        f"{ALGORITMO} Credential={id_chave}/{escopo}, SignedHeaders={assinados}, Signature={assinatura}"
    )
    return todos
