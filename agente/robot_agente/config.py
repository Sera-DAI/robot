"""Configuração do agente fora do Git: um arquivo JSON na pasta de dados do usuário, sem segredo."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .erros import ConfigErro

PASTA = "robot-agente"
ARQUIVO = "config.json"


def pasta_de_dados() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / PASTA


def ler_url_da_fila(pasta: Path | None = None) -> str:
    arquivo = (pasta or pasta_de_dados()) / ARQUIVO
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        url = dados["fila_url"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigErro("configuração ausente ou inválida; rode: python -m robot_agente.configurar") from None
    if not isinstance(url, str):
        raise ConfigErro("configuração inválida; rode: python -m robot_agente.configurar")
    return url


def gravar_url_da_fila(url: str, pasta: Path | None = None) -> Path:
    destino = pasta or pasta_de_dados()
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / ARQUIVO
    arquivo.write_text(json.dumps({"fila_url": url}, indent=2) + "\n", encoding="utf-8")
    return arquivo
