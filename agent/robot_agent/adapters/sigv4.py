"""AWS Signature Version 4 signing using only the standard library.

The agent runs with the power to shut the PC down, so it depends on no third-party package.
Nothing here logs or returns the secret.
"""
from __future__ import annotations

import hashlib
import hmac

ALGORITHM = "AWS4-HMAC-SHA256"


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    key = _hmac(("AWS4" + secret).encode("utf-8"), date)
    for part in (region, service, "aws4_request"):
        key = _hmac(key, part)
    return key


def sign_post(
    *, host: str, path: str, headers: dict[str, str], body: bytes,
    key_id: str, secret: str, region: str, service: str, instant: str,
) -> dict[str, str]:
    """Returns the POST headers with Authorization already added.

    `instant` is in the format YYYYMMDDTHHMMSSZ (UTC). No query string: SQS uses a JSON body.
    """
    date = instant[:8]
    all_headers = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    all_headers["host"] = host
    all_headers["x-amz-date"] = instant
    names = sorted(all_headers)
    canonical = "".join(f"{name}:{all_headers[name]}\n" for name in names)
    signed = ";".join(names)
    request = "\n".join(["POST", path, "", canonical, signed, hashlib.sha256(body).hexdigest()])
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join([ALGORITHM, instant, scope, hashlib.sha256(request.encode("utf-8")).hexdigest()])
    signature = hmac.new(
        signing_key(secret, date, region, service), to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    all_headers["authorization"] = (
        f"{ALGORITHM} Credential={key_id}/{scope}, SignedHeaders={signed}, Signature={signature}"
    )
    return all_headers
