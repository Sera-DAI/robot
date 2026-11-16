"""Agent configuration kept out of Git: a JSON file in the user's data folder, with no secret."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import ConfigError

FOLDER = "robot-agente"  # persisted name, kept so existing installations keep working
FILE = "config.json"
KEY = "queue_url"
LEGACY_KEY = "fila_url"  # written by earlier versions; still accepted when reading


def data_folder() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / FOLDER


def read_queue_url(folder: Path | None = None) -> str:
    file = (folder or data_folder()) / FILE
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        url = data[KEY] if KEY in data else data[LEGACY_KEY]
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigError("configuration missing or invalid; run: python -m robot_agent.configure") from None
    if not isinstance(url, str):
        raise ConfigError("invalid configuration; run: python -m robot_agent.configure")
    return url


def write_queue_url(url: str, folder: Path | None = None) -> Path:
    target = folder or data_folder()
    target.mkdir(parents=True, exist_ok=True)
    file = target / FILE
    file.write_text(json.dumps({KEY: url}, indent=2) + "\n", encoding="utf-8")
    return file
