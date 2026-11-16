"""The only place in the agent that runs a process. Fixed commands, no shell, no text from the queue."""
from __future__ import annotations

import os
import subprocess

from ..errors import ShutdownError

WARNING_S = 30  # time to cancel with "shutdown /a"; after the delay, Windows force-closes programs

# Action from the fixed list -> full command line. Nothing here comes from outside.
_COMMANDS: dict[str, tuple[str, ...]] = {
    "shutdown": ("/s", "/t", str(WARNING_S), "/c", "Robot: shutting down at Alexa's request"),
}


def _executable() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", "shutdown.exe")


def execute(action: str) -> None:
    arguments = _COMMANDS.get(action)
    if arguments is None:
        raise ShutdownError("action outside the fixed list")
    try:
        result = subprocess.run([_executable(), *arguments], shell=False, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise ShutdownError("could not call the Windows shutdown") from None
    if result.returncode != 0:
        raise ShutdownError(f"Windows refused the shutdown (code {result.returncode})")
