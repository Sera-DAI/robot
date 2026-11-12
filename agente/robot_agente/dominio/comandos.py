"""Regras puras do agente: que mensagem da fila vira ação, e quando ela é velha demais.

Sem I/O. A lista de ações é fixa: o agente nunca executa texto vindo da fila.
"""
from __future__ import annotations

import json

VERSAO = 1
ACAO_DESLIGAR = "shutdown"
ACOES = frozenset({ACAO_DESLIGAR})

VALIDADE_MS = 60_000  # igual à retenção da fila: comando mais velho que isso é descartado
TAMANHO_MAXIMO = 256


def interpretar(corpo: object) -> str | None:
    """Devolve a ação pedida, ou None se a mensagem não for exatamente um comando conhecido."""
    if not isinstance(corpo, str) or len(corpo) > TAMANHO_MAXIMO:
        return None
    try:
        dados = json.loads(corpo)
    except ValueError:
        return None
    if not isinstance(dados, dict) or set(dados) != {"versao", "acao"}:
        return None
    if type(dados["versao"]) is not int or dados["versao"] != VERSAO:
        return None
    acao = dados["acao"]
    if not isinstance(acao, str) or acao not in ACOES:
        return None
    return acao


def esta_valida(enviada_em_ms: object, agora_ms: int, inicio_agente_ms: int) -> bool:
    """Só vale comando enviado depois que o agente subiu e há menos de VALIDADE_MS.

    Sem isso, um "desligar" dito com o PC desligado poderia derrubar o PC logo após ligar.
    """
    if type(enviada_em_ms) is not int:
        return False
    if enviada_em_ms < inicio_agente_ms:
        return False
    return agora_ms - enviada_em_ms <= VALIDADE_MS
