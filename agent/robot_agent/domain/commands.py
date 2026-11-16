"""Pure agent rules: which queue message becomes an action, and when it is too old.

No I/O. The list of actions is fixed: the agent never executes text coming from the queue.
"""
from __future__ import annotations

import json

VERSION = 1
ACTION_SHUTDOWN = "shutdown"
ACTIONS = frozenset({ACTION_SHUTDOWN})

VALIDITY_MS = 60_000  # same as the queue retention: a command older than this is discarded
MAX_SIZE = 256


def interpret(body: object) -> str | None:
    """Returns the requested action, or None if the message is not exactly a known command."""
    if not isinstance(body, str) or len(body) > MAX_SIZE:
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict) or set(data) != {"version", "action"}:
        return None
    if type(data["version"]) is not int or data["version"] != VERSION:
        return None
    action = data["action"]
    if not isinstance(action, str) or action not in ACTIONS:
        return None
    return action


def is_valid(sent_at_ms: object, now_ms: int, agent_start_ms: int) -> bool:
    """A command only counts if it was sent after the agent started and less than VALIDITY_MS ago.

    Without this, a "turn off" said while the PC was off could bring the PC down right after it starts.
    """
    if type(sent_at_ms) is not int:
        return False
    if sent_at_ms < agent_start_ms:
        return False
    return now_ms - sent_at_ms <= VALIDITY_MS
