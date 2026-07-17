"""Private-data transient map helpers for sensitive Fabric collection writes."""
from __future__ import annotations

import base64
from typing import Any

from app.blockchain.common.hashing import canonical_json_bytes


def transient_json(key: str, payload: Any) -> dict[str, str]:
    if not key or any(character.isspace() for character in key):
        raise ValueError("transient key must be a non-empty token")
    encoded = base64.b64encode(canonical_json_bytes(payload)).decode("ascii")
    return {key: encoded}
