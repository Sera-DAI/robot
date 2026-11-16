"""Commands sent to the PC agent through the queue. Fixed list: nothing outside it is built.

No I/O. The agent keeps its own copy of this list and refuses what it does not know.
"""
from __future__ import annotations

from typing import Any

VERSION = 1
ACTION_SHUTDOWN = "shutdown"
ACTIONS = frozenset({ACTION_SHUTDOWN})


def build(action: str) -> dict[str, Any]:
    """Body of the queue message. Raises ValueError for an action outside the list."""
    if action not in ACTIONS:
        raise ValueError("action outside the fixed list")
    return {"version": VERSION, "action": action}
