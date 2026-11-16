"""Agent loop: receives from the queue, validates, deletes and only then executes. Thin, no I/O of its own."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from .domain import commands
from .errors import QueueError, ShutdownError

LOG = logging.getLogger("robot_agent")

INITIAL_WAIT_S = 5
MAX_WAIT_S = 300


class Queue(Protocol):
    def receive(self) -> list: ...
    def delete(self, receipt: str) -> None: ...


@dataclass
class Deps:
    queue: Queue
    execute: Callable[[str], None]
    now_ms: Callable[[], int]
    sleep: Callable[[float], None]


def cycle(d: Deps, start_ms: int) -> int:
    """One receive from the queue. Returns how many actions were executed."""
    executed = 0
    for message in d.queue.receive():
        action = commands.interpret(message.body)
        valid = action is not None and commands.is_valid(message.sent_at_ms, d.now_ms(), start_ms)
        # Delete before acting: if deleting fails, nothing is executed and the command never runs twice.
        try:
            d.queue.delete(message.receipt)
        except QueueError as error:
            LOG.error("message not deleted, nothing was executed: %s", error)
            continue
        if action is None:
            LOG.warning("message discarded: not a command from the fixed list")
            continue
        if not valid:
            LOG.warning("command '%s' discarded: sent before the agent started or too old", action)
            continue
        if executed:
            LOG.info("command '%s' repeated in the same batch, ignored", action)
            continue
        try:
            d.execute(action)
        except ShutdownError as error:
            LOG.error("command '%s' failed: %s", action, error)
            continue
        LOG.info("command '%s' executed", action)
        executed += 1
    return executed


def run(d: Deps, keep_going: Callable[[], bool] = lambda: True) -> None:
    """Runs until `keep_going` returns False. A queue error waits and tries again, with backoff."""
    start_ms = d.now_ms()
    wait = INITIAL_WAIT_S
    LOG.info("agent started")
    while keep_going():
        try:
            cycle(d, start_ms)
            wait = INITIAL_WAIT_S
        except QueueError as error:
            LOG.error("queue unavailable (%s); retrying in %s s", error, wait)
            d.sleep(wait)
            wait = min(wait * 2, MAX_WAIT_S)
