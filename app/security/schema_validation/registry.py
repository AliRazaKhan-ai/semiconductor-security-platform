"""Purpose: Register immutable JSON schemas used by the public API.
Directory: app/security/schema_validation.
Dependencies: Python standard library.
Connection: Supplies schemas to the request validator without filesystem ambiguity.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_SCAN_SUBMISSION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["chip_id", "evidence"],
    "properties": {
        "scan_id": {
            "type": "string",
            "minLength": 8,
            "maxLength": 128,
            "pattern": "^[A-Za-z0-9._:-]+$",
        },
        "chip_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "pattern": "^[A-Za-z0-9._:-]+$",
        },
        "chip_file": {"type": "string", "maxLength": 255},
        "source": {"type": "object", "additionalProperties": True},
        "evidence": {"type": "object", "minProperties": 1, "additionalProperties": True},
        "metadata": {"type": "object", "additionalProperties": True},
    },
}

_SCHEMAS: dict[str, dict[str, Any]] = {"scan_submission": _SCAN_SUBMISSION_SCHEMA}


def get_schema(name: str) -> dict[str, Any]:
    try:
        return deepcopy(_SCHEMAS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown JSON schema: {name}") from exc

