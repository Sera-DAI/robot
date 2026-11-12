"""Configuração inicial: python -m robot_agente.configurar

Pergunta a URL da fila e a chave de acesso do usuário robot-agente. O segredo é digitado
sem eco e vai direto para o Credential Manager: não passa por arquivo nem pelo histórico do terminal.
"""
from __future__ import annotations

import getpass
import re
import sys

from . import config
from .adaptadores import credenciais
from .adaptadores.sqs import regiao_da_url
from .erros import AgenteErro

FORMATO_ID = re.compile(r"^[A-Z0-9]{16,32}$")


def main() -> int:
    try:
        url = input("URL da fila (saída FilaUrl do sam deploy): ").strip()
        regiao_da_url(url)
        id_chave = input("ID da chave de acesso do robot-agente: ").strip()
        if not FORMATO_ID.match(id_chave):
            print("ID da chave fora do formato esperado.")
            return 2
        segredo = getpass.getpass("Segredo da chave (não aparece na tela): ").strip()
        if not segredo:
            print("Segredo vazio.")
            return 2
        credenciais.gravar(id_chave, segredo)
        arquivo = config.gravar_url_da_fila(url)
    except AgenteErro as erro:
        print(f"Não configurado: {erro}")
        return 2
    print(f"Credencial gravada no Credential Manager (alvo '{credenciais.ALVO}').")
    print(f"URL da fila gravada em {arquivo}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
