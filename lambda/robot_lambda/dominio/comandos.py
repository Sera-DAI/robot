"""Comandos enviados ao agente do PC pela fila. Lista fixa: nada fora dela é montado.

Sem I/O. O agente mantém a própria cópia desta lista e recusa o que não conhece.
"""
from __future__ import annotations

from typing import Any

VERSAO = 1
ACAO_DESLIGAR = "shutdown"
ACOES = frozenset({ACAO_DESLIGAR})


def montar(acao: str) -> dict[str, Any]:
    """Corpo da mensagem da fila. Levanta ValueError para ação fora da lista."""
    if acao not in ACOES:
        raise ValueError("ação fora da lista fixa")
    return {"versao": VERSAO, "acao": acao}
