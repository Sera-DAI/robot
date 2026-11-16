"""AcceptGrant tokens in DynamoDB. Personal skill: a single record, the owner's."""
from __future__ import annotations

from typing import Any

from ..errors import StorageError

# Persisted names, kept as they were first stored so the existing record stays readable.
RECORD_ID = "dono"
EXPIRY_ATTRIBUTE = "expira_em"


class DynamoTokens:
    def __init__(self, table_name: str, resource: Any = None):
        if resource is None:
            import boto3  # imported here so the tests do not need the SDK

            resource = boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def get(self) -> dict[str, Any] | None:
        try:
            item = self._table.get_item(Key={"id": RECORD_ID}).get("Item")
            if not item:
                return None
            return {
                "access_token": item["access_token"],
                "refresh_token": item["refresh_token"],
                "expires_at": int(item[EXPIRY_ATTRIBUTE]),  # DynamoDB returns a Decimal
            }
        except Exception:
            raise StorageError("failed to read the tokens") from None

    def save(self, record: dict[str, Any]) -> None:
        try:
            self._table.put_item(
                Item={
                    "id": RECORD_ID,
                    "access_token": record["access_token"],
                    "refresh_token": record["refresh_token"],
                    EXPIRY_ATTRIBUTE: int(record["expires_at"]),
                }
            )
        except Exception:
            raise StorageError("failed to write the tokens") from None
