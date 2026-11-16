"""Minimal SQS queue client (JSON protocol), with only receive and delete.

Never logs the credential, the authorization header or a response body.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ..errors import QueueError
from . import sigv4

# The queue URL can only point to AWS SQS: the signature never goes to another address.
URL_FORMAT = re.compile(r"^https://sqs\.([a-z]{2}(?:-[a-z]+)+-\d)\.amazonaws\.com/\d{12}/[A-Za-z0-9_-]{1,80}$")
WAIT_S = 20  # long polling: one call every 20 s while the queue is empty


@dataclass(frozen=True)
class Message:
    body: str
    receipt: str
    sent_at_ms: int | None


def region_from_url(url: str) -> str:
    found = URL_FORMAT.match(url) if isinstance(url, str) else None
    if not found:
        raise QueueError("queue URL outside the expected format")
    return found.group(1)


def _now_amz() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class SqsClient:
    def __init__(self, url: str, key_id: str, secret: str, now_amz: Callable[[], str] = _now_amz):
        self._region = region_from_url(url)
        self._url = url
        self._host = f"sqs.{self._region}.amazonaws.com"
        self._key_id = key_id
        self._secret = secret
        self._now_amz = now_amz

    def receive(self) -> list[Message]:
        data = self._call(
            "ReceiveMessage",
            {
                "QueueUrl": self._url,
                "MaxNumberOfMessages": 10,
                "WaitTimeSeconds": WAIT_S,
                "MessageSystemAttributeNames": ["SentTimestamp"],
            },
            timeout_s=WAIT_S + 15,
        )
        messages = []
        for raw in data.get("Messages") or []:
            if not isinstance(raw, dict) or not isinstance(raw.get("ReceiptHandle"), str):
                continue
            attributes = raw.get("Attributes") if isinstance(raw.get("Attributes"), dict) else {}
            sent = attributes.get("SentTimestamp")
            messages.append(
                Message(
                    body=raw.get("Body") if isinstance(raw.get("Body"), str) else "",
                    receipt=raw["ReceiptHandle"],
                    sent_at_ms=int(sent) if isinstance(sent, str) and sent.isdigit() else None,
                )
            )
        return messages

    def delete(self, receipt: str) -> None:
        self._call("DeleteMessage", {"QueueUrl": self._url, "ReceiptHandle": receipt}, timeout_s=15)

    def _call(self, operation: str, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = sigv4.sign_post(
            host=self._host, path="/", body=body,
            headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": f"AmazonSQS.{operation}"},
            key_id=self._key_id, secret=self._secret,
            region=self._region, service="sqs", instant=self._now_amz(),
        )
        headers.pop("host")  # urllib sets Host from the URL
        request = urllib.request.Request(f"https://{self._host}/", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                text = response.read()
            data = json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as error:
            # Status only: the error body may repeat request data.
            raise QueueError(f"the queue answered {operation} with HTTP {error.code}") from None
        except Exception:
            raise QueueError(f"network or format failure in {operation}") from None
        if not isinstance(data, dict):
            raise QueueError(f"unexpected response in {operation}")
        return data
