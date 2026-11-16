"""SQS queue of commands for the PC agent. It only sends; the agent is the consumer."""
from __future__ import annotations

import json
from typing import Any

from ..errors import QueueError


class SqsQueue:
    def __init__(self, url: str, client: Any = None):
        if client is None:
            import boto3  # imported here so the tests do not need the SDK

            client = boto3.client("sqs")
        self._url = url
        self._client = client

    def send(self, command: dict[str, Any]) -> None:
        try:
            self._client.send_message(QueueUrl=self._url, MessageBody=json.dumps(command))
        except Exception:
            raise QueueError("failed to send the command to the queue") from None
