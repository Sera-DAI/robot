"""Chave de acesso do agente no Credential Manager do Windows (credencial genérica).

O usuário da credencial é o ID da chave de acesso e a senha é o segredo. Nada vai para arquivo.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from ..erros import CredencialErro

ALVO = "robot-agente"
_TIPO_GENERICA = 1
_PERSISTE_NA_MAQUINA = 2


class _Credencial(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _advapi():
    if sys.platform != "win32":
        raise CredencialErro("o Credential Manager só existe no Windows")
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credencial))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credencial), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def ler(alvo: str = ALVO) -> tuple[str, str]:
    """Devolve (id da chave, segredo). Levanta CredencialErro se não houver credencial."""
    api = _advapi()
    ponteiro = ctypes.POINTER(_Credencial)()
    if not api.CredReadW(alvo, _TIPO_GENERICA, 0, ctypes.byref(ponteiro)):
        raise CredencialErro("credencial não encontrada no Credential Manager deste usuário")
    try:
        credencial = ponteiro.contents
        id_chave = credencial.UserName or ""
        segredo = ctypes.string_at(credencial.CredentialBlob, credencial.CredentialBlobSize).decode("utf-16-le")
    except Exception:
        raise CredencialErro("credencial ilegível") from None
    finally:
        api.CredFree(ponteiro)
    if not id_chave or not segredo:
        raise CredencialErro("credencial incompleta")
    return id_chave, segredo


def gravar(id_chave: str, segredo: str, alvo: str = ALVO) -> None:
    api = _advapi()
    dados = segredo.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(dados)).from_buffer_copy(dados)
    credencial = _Credencial()
    credencial.Type = _TIPO_GENERICA
    credencial.TargetName = alvo
    credencial.Comment = "Robot: chave do agente que le a fila de comandos"
    credencial.CredentialBlobSize = len(dados)
    credencial.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credencial.Persist = _PERSISTE_NA_MAQUINA
    credencial.UserName = id_chave
    if not api.CredWriteW(ctypes.byref(credencial), 0):
        raise CredencialErro("o Windows recusou a gravação da credencial")
