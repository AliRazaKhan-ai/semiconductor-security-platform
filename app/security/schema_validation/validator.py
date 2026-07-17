"""Purpose: Validate API JSON payloads using JSON Schema 2020-12.
Directory: app/security/schema_validation.
Dependencies: jsonschema, app.exceptions.
Connection: Called by write routes before any event is persisted.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from app.exceptions import ValidationError
from app.security.schema_validation.registry import get_schema


def validate_payload(name: str, payload: Any) -> None:
    validator = Draft202012Validator(get_schema(name))
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    details = []
    for error in errors:
        path = ".".join(str(item) for item in error.absolute_path) or "$"
        details.append({"path": path, "message": error.message})
    raise ValidationError("JSON payload failed schema validation", {"errors": details})

