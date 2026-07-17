"""Canonical hashing primitives shared by Fabric and Ethereum integrations."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically for cryptographic hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes | str | Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def require_sha256(value: str, *, field: str = "hash") -> str:
    normalized = str(value).lower().removeprefix("0x")
    if not _HEX_64.fullmatch(normalized):
        raise ValueError(f"{field} must be a 32-byte SHA-256 hexadecimal value")
    return normalized


def bytes32_hex(value: str) -> str:
    return "0x" + require_sha256(value)


def provenance_digest(record: dict[str, Any]) -> str:
    """Hash the exact Fabric provenance document submitted to the permissioned ledger."""
    return sha256_hex(record)
