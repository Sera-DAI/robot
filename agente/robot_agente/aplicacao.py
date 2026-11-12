"""Laço do agente: recebe da fila, valida, apaga e só então executa. Fino, sem I/O próprio."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from .dominio import comandos
from .erros import DesligamentoErro, FilaErro

LOG = logging.getLogger("robot_agente")

ESPERA_INICIAL_S = 5
ESPERA_MAXIMA_S = 300


class Fila(Protocol):
    def receber(self) -> list: ...
    def apagar(self, recibo: str) -> None: ...


@dataclass
class Deps:
    fila: Fila
    executar: Callable[[str], None]
    agora_ms: Callable[[], int]
    dormir: Callable[[float], None]


def ciclo(d: Deps, inicio_ms: int) -> int:
    """Um recebimento da fila. Devolve quantas ações foram executadas."""
    executadas = 0
    for mensagem in d.fila.receber():
        acao = comandos.interpretar(mensagem.corpo)
        valida = acao is not None and comandos.esta_valida(mensagem.enviada_em_ms, d.agora_ms(), inicio_ms)
        # Apaga antes de agir: se apagar falhar, nada é executado e o comando nunca roda duas vezes.
        try:
            d.fila.apagar(mensagem.recibo)
        except FilaErro as erro:
            LOG.error("mensagem não apagada, nada foi executado: %s", erro)
            continue
        if acao is None:
            LOG.warning("mensagem descartada: não é um comando da lista fixa")
            continue
        if not valida:
            LOG.warning("comando '%s' descartado: enviado antes de o agente subir ou velho demais", acao)
            continue
        if executadas:
            LOG.info("comando '%s' repetido no mesmo lote, ignorado", acao)
            continue
        try:
            d.executar(acao)
        except DesligamentoErro as erro:
            LOG.error("comando '%s' falhou: %s", acao, erro)
            continue
        LOG.info("comando '%s' executado", acao)
        executadas += 1
    return executadas


def rodar(d: Deps, continuar: Callable[[], bool] = lambda: True) -> None:
    """Roda até `continuar` devolver False. Erro de fila espera e tenta de novo, com recuo."""
    inicio_ms = d.agora_ms()
    espera = ESPERA_INICIAL_S
    LOG.info("agente iniciado")
    while continuar():
        try:
            ciclo(d, inicio_ms)
            espera = ESPERA_INICIAL_S
        except FilaErro as erro:
            LOG.error("fila indisponível (%s); nova tentativa em %s s", erro, espera)
            d.dormir(espera)
            espera = min(espera * 2, ESPERA_MAXIMA_S)
