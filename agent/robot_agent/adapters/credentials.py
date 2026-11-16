"""The agent's access key in the Windows Credential Manager (generic credential).

The credential's user name is the access key ID and its password is the secret. Nothing goes to a file.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from ..errors import CredentialError

TARGET = "robot-agente"  # persisted name, kept so existing installations keep working
_TYPE_GENERIC = 1
_PERSIST_LOCAL_MACHINE = 2


class _Credential(ctypes.Structure):
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
        raise CredentialError("the Credential Manager only exists on Windows")
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def read(target: str = TARGET) -> tuple[str, str]:
    """Returns (key ID, secret). Raises CredentialError if there is no credential."""
    api = _advapi()
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, _TYPE_GENERIC, 0, ctypes.byref(pointer)):
        raise CredentialError("credential not found in this user's Credential Manager")
    try:
        credential = pointer.contents
        key_id = credential.UserName or ""
        secret = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-16-le")
    except Exception:
        raise CredentialError("unreadable credential") from None
    finally:
        api.CredFree(pointer)
    if not key_id or not secret:
        raise CredentialError("incomplete credential")
    return key_id, secret


def write(key_id: str, secret: str, target: str = TARGET) -> None:
    api = _advapi()
    data = secret.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    credential = _Credential()
    credential.Type = _TYPE_GENERIC
    credential.TargetName = target
    credential.Comment = "Robot: key of the agent that reads the command queue"
    credential.CredentialBlobSize = len(data)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _PERSIST_LOCAL_MACHINE
    credential.UserName = key_id
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise CredentialError("Windows refused to write the credential")
