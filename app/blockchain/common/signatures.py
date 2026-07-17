"""HMAC integrity signatures for local blockchain receipts and configuration manifests."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.blockchain.common.hashing import canonical_json_bytes


def sign_payload(payload: Any, secret: bytes) -> str:
    if len(secret) < 32:
        raise ValueError("integrity secret must contain at least 32 bytes")
    return hmac.new(secret, canonical_json_bytes(payload), hashlib.sha256).hexdigest()


def verify_payload(payload: Any, signature: str, secret: bytes) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, str(signature).lower())
