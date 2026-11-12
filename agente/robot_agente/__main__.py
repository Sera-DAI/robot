"""Entrada do agente: python -m robot_agente. Monta as dependências reais e roda o laço."""
from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from . import config
from .adaptadores import credenciais, desligamento
from .adaptadores.sqs import ClienteSqs
from .aplicacao import LOG, Deps, rodar
from .erros import AgenteErro


def _configurar_log() -> None:
    pasta = config.pasta_de_dados()
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = RotatingFileHandler(pasta / "agente.log", maxBytes=200_000, backupCount=2, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(arquivo)
    LOG.setLevel(logging.INFO)


def main() -> int:
    _configurar_log()
    try:
        url = config.ler_url_da_fila()
        id_chave, segredo = credenciais.ler()
        fila = ClienteSqs(url, id_chave, segredo)
    except AgenteErro as erro:
        LOG.error("agente não iniciou: %s", erro)
        return 2
    try:
        rodar(Deps(fila=fila, executar=desligamento.executar, agora_ms=lambda: int(time.time() * 1000), dormir=time.sleep))
    except KeyboardInterrupt:
        LOG.info("agente encerrado")
    except Exception as erro:  # o agendador reinicia; o tipo basta para o diagnóstico
        LOG.error("agente parou por erro inesperado: %s", type(erro).__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
