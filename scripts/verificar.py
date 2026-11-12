#!/usr/bin/env python3
"""Verificação local e do CI.

--rapido   : regras de arquitetura (Lambda e agente), varredura de segredos e testes do domínio.
--completo : o mesmo, com todos os testes.

Sai com código diferente de zero se qualquer verificação falhar.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOMINIO = RAIZ / "lambda" / "robot_lambda" / "dominio"
TESTES = RAIZ / "lambda" / "tests"
CODIGO_LAMBDA = RAIZ / "lambda"
CODIGO_AGENTE = RAIZ / "agente"
AGENTE = CODIGO_AGENTE / "robot_agente"
DOMINIO_AGENTE = AGENTE / "dominio"
TESTES_AGENTE = CODIGO_AGENTE / "tests_agente"
# Pastas de teste com nomes diferentes: duas pastas "tests" colidiriam no mesmo processo.
SUITES = [(TESTES, CODIGO_LAMBDA), (TESTES_AGENTE, CODIGO_AGENTE)]

# No agente, só este arquivo pode executar processo. Ele roda com poder de desligar o PC.
EXECUTOR_DO_AGENTE = "adaptadores/desligamento.py"
MODULOS_DE_EXECUCAO = {"subprocess", "pty", "pexpect", "multiprocessing"}
FUNCOES_PROIBIDAS_NO_AGENTE = {"eval", "exec", "compile", "__import__"}  # chamadas pelo nome
METODOS_PROIBIDOS_NO_AGENTE = {  # chamados como atributo, por exemplo os.system
    "system", "popen", "startfile",
    "execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp", "fork", "ShellExecuteW", "WinExec", "CreateProcessW", "CreateProcessA",
}
# ctypes dá acesso à API do Windows inteira: só o leitor do Credential Manager pode usar.
ARQUIVO_COM_CTYPES = "adaptadores/credenciais.py"
PACOTE_DO_AGENTE = "robot_agente"

# O domínio é puro: sem I/O e sem depender dos adaptadores.
IMPORTS_PROIBIDOS_NO_DOMINIO = {
    "boto3", "botocore", "urllib", "http", "requests", "socket", "subprocess",
    "os", "shutil", "pathlib", "ssl", "ctypes", "robot_lambda.adaptadores", "adaptadores",
}

EMAIL_OK = ("noreply", "example.")
MAC_FICTICIO = {"00-14-22-01-23-45"}
EXTENSOES_TEXTO = {
    ".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt", ".ps1", ".cfg", ".ini", ".gitignore",
}

PADROES_SEGREDO = [
    ("chave de acesso AWS", re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b")),
    ("client id do LWA", re.compile(r"amzn1\.application-oa2-client\.[0-9a-f]{32}")),
    ("id de skill Alexa", re.compile(r"amzn1\.ask\.skill\.[0-9a-f-]{36}")),
    ("token do LWA", re.compile(r"\bAtz[ra]\|[A-Za-z0-9_\-]{20,}")),
    ("chave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("caminho local do Windows", re.compile(r"\b[A-Za-z]:\\Users\\")),
    ("caminho local do Linux", re.compile(r"(?<![\w.])/home/[A-Za-z]")),
    ("e-mail", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("endereço MAC", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
]


def _modulos_importados(codigo: str) -> set[str]:
    arvore = ast.parse(codigo)
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            base = ("." * no.level) + (no.module or "")
            achados.add(base)
            achados.update(f"{base}.{a.name}" for a in no.names)
    return achados


def checar_dependencias(pasta: Path) -> list[str]:
    """Erros de importação proibida nos arquivos do domínio."""
    erros: list[str] = []
    if not pasta.exists():
        return erros
    for arquivo in sorted(pasta.rglob("*.py")):
        for modulo in _modulos_importados(arquivo.read_text(encoding="utf-8")):
            limpo = modulo.lstrip(".")
            topo = limpo.split(".")[0]
            if limpo in IMPORTS_PROIBIDOS_NO_DOMINIO or topo in IMPORTS_PROIBIDOS_NO_DOMINIO:
                erros.append(f"{arquivo}: o domínio não pode importar '{modulo}'")
            elif "adaptadores" in limpo.split("."):
                erros.append(f"{arquivo}: o domínio não pode importar '{modulo}'")
    return erros


def checar_agente(pasta: Path) -> list[str]:
    """Erros de execução de processo ou de código fora do único executor do agente."""
    erros: list[str] = []
    if not pasta.exists():
        return erros
    for arquivo in sorted(pasta.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        e_o_executor = arquivo.relative_to(pasta).as_posix() == EXECUTOR_DO_AGENTE
        relativo = arquivo.relative_to(pasta).as_posix()
        for modulo in _modulos_importados(ast.unparse(arvore)):
            topo = modulo.lstrip(".").split(".")[0]
            if topo in MODULOS_DE_EXECUCAO and not e_o_executor:
                erros.append(f"{arquivo}: só {EXECUTOR_DO_AGENTE} pode importar '{modulo}'")
            elif topo == "ctypes" and relativo != ARQUIVO_COM_CTYPES:
                erros.append(f"{arquivo}: só {ARQUIVO_COM_CTYPES} pode importar '{modulo}'")
            elif not modulo.startswith(".") and topo != PACOTE_DO_AGENTE and topo not in sys.stdlib_module_names:
                erros.append(f"{arquivo}: o agente usa só a biblioteca padrão, não '{modulo}'")
            if modulo.split(".")[-1] in METODOS_PROIBIDOS_NO_AGENTE:
                erros.append(f"{arquivo}: importação proibida no agente: '{modulo}'")
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call):
                alvo = no.func
                nome = ""
                if isinstance(alvo, ast.Name) and alvo.id in FUNCOES_PROIBIDAS_NO_AGENTE | METODOS_PROIBIDOS_NO_AGENTE:
                    nome = alvo.id
                elif isinstance(alvo, ast.Attribute) and alvo.attr in METODOS_PROIBIDOS_NO_AGENTE:
                    nome = alvo.attr
                if nome:
                    erros.append(f"{arquivo}:{no.lineno}: chamada proibida no agente: '{nome}'")
                for argumento in no.keywords:
                    if argumento.arg is None:
                        erros.append(f"{arquivo}:{no.lineno}: o agente não passa argumentos por ** em chamadas")
                    elif argumento.arg == "shell" and not (
                        isinstance(argumento.value, ast.Constant) and argumento.value.value is False
                    ):
                        erros.append(f"{arquivo}:{no.lineno}: o agente nunca usa shell")
    return erros


def _arquivos_versionados(raiz: Path) -> list[Path]:
    try:
        saida = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "-co", "--exclude-standard"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        return [raiz / linha for linha in saida if linha]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in raiz.rglob("*") if p.is_file() and ".git" not in p.parts]


def checar_segredos(raiz: Path, arquivos: list[Path] | None = None) -> list[str]:
    """Erros de dado sensível em arquivos de texto. Nunca imprime o valor achado."""
    erros: list[str] = []
    for arquivo in arquivos if arquivos is not None else _arquivos_versionados(raiz):
        if arquivo.suffix.lower() not in EXTENSOES_TEXTO or not arquivo.is_file():
            continue
        try:
            linhas = arquivo.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for numero, linha in enumerate(linhas, start=1):
            for nome, padrao in PADROES_SEGREDO:
                for achado in padrao.finditer(linha):
                    texto = achado.group(0)
                    if nome == "e-mail" and any(ok in texto.lower() for ok in EMAIL_OK):
                        continue
                    if nome == "endereço MAC" and texto.lower() in MAC_FICTICIO:
                        continue
                    erros.append(f"{arquivo}:{numero}: possível {nome}")
    return erros


def _rodar_testes(padrao: str) -> bool:
    tudo_ok = True
    for pasta, topo in SUITES:
        if not pasta.exists():
            print(f"FALHA: sem a pasta de testes {pasta}")
            tudo_ok = False
            continue
        sys.path.insert(0, str(topo))
        suite = unittest.defaultTestLoader.discover(str(pasta), pattern=padrao, top_level_dir=str(topo))
        if suite.countTestCases() == 0:
            print(f"FALHA: nenhum teste encontrado em {pasta}")
            tudo_ok = False
        elif not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
            tudo_ok = False
    return tudo_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--rapido", action="store_true")
    modo.add_argument("--completo", action="store_true")
    args = parser.parse_args(argv)

    falhas: list[str] = []
    falhas += checar_dependencias(DOMINIO)
    falhas += checar_dependencias(DOMINIO_AGENTE)
    falhas += checar_agente(AGENTE)
    falhas += checar_segredos(RAIZ)
    for falha in falhas:
        print(f"FALHA: {falha}")

    padrao = "test_*.py" if args.completo else "test_dominio*.py"
    testes_ok = _rodar_testes(padrao)
    if falhas or not testes_ok:
        print("verificação reprovada")
        return 1
    print("verificação aprovada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
