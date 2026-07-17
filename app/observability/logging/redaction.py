"""Purpose: Remove sensitive fields before structured log serialisation.
Directory: app/observability/logging.
Dependencies: Python collections.
Connection: Used by the JSON formatter and request logging hooks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"


def redact(value: Any, fields: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if str(key).lower() in fields else redact(item, fields)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item, fields) for item in value]
    return value

