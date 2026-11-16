"""Agent entry point: python -m robot_agent. Builds the real dependencies and runs the loop."""
from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from . import config
from .adapters import credentials, shutdown
from .adapters.sqs import SqsClient
from .application import LOG, Deps, run
from .errors import AgentError


def _configure_log() -> None:
    folder = config.data_folder()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "agent.log", maxBytes=200_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)


def main() -> int:
    _configure_log()
    try:
        url = config.read_queue_url()
        key_id, secret = credentials.read()
        queue = SqsClient(url, key_id, secret)
    except AgentError as error:
        LOG.error("agent did not start: %s", error)
        return 2
    try:
        run(Deps(queue=queue, execute=shutdown.execute, now_ms=lambda: int(time.time() * 1000), sleep=time.sleep))
    except KeyboardInterrupt:
        LOG.info("agent stopped")
    except Exception as error:  # the scheduler restarts it; the type is enough for diagnosis
        LOG.error("agent stopped by an unexpected error: %s", type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
