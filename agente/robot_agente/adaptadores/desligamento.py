"""Único lugar do agente que executa processo. Comandos fixos, sem shell e sem texto da fila."""
from __future__ import annotations

import os
import subprocess

from ..erros import DesligamentoErro

AVISO_S = 30  # tempo para cancelar com "shutdown /a"; com prazo, o Windows fecha os programas à força

# Ação da lista fixa -> linha de comando completa. Nada aqui vem de fora.
_COMANDOS: dict[str, tuple[str, ...]] = {
    "shutdown": ("/s", "/t", str(AVISO_S), "/c", "Robot: desligando a pedido da Alexa"),
}


def _executavel() -> str:
    raiz = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(raiz, "System32", "shutdown.exe")


def executar(acao: str) -> None:
    argumentos = _COMANDOS.get(acao)
    if argumentos is None:
        raise DesligamentoErro("ação fora da lista fixa")
    try:
        resultado = subprocess.run([_executavel(), *argumentos], shell=False, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise DesligamentoErro("não foi possível chamar o desligamento do Windows") from None
    if resultado.returncode != 0:
        raise DesligamentoErro(f"o Windows recusou o desligamento (código {resultado.returncode})")
