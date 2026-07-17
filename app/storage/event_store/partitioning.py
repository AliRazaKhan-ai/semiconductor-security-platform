"""Purpose: Produce safe partitioned paths for scan event journals.
Directory: app/storage/event_store.
Dependencies: hashlib, pathlib, datetime.
Connection: Used by writer for new scans and recovery for path validation.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from app.exceptions import ValidationError

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def validate_identifier(value: str, field: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValidationError(
            f"Invalid {field}",
            {"field": field, "constraint": "1-128 characters: A-Z, a-z, 0-9, dot, underscore, colon, hyphen"},
        )
    return value


def scan_event_path(root: Path, scan_id: str, timestamp: datetime | None = None) -> Path:
    validate_identifier(scan_id, "scan_id")
    instant = timestamp or datetime.now(UTC)
    digest = hashlib.sha256(scan_id.encode("utf-8")).hexdigest()[:2]
    return root / f"{instant.year:04d}" / f"{instant.month:02d}" / digest / f"{scan_id}.jsonl"


def scan_lock_path(lock_root: Path, scan_id: str) -> Path:
    validate_identifier(scan_id, "scan_id")
    digest = hashlib.sha256(scan_id.encode("utf-8")).hexdigest()
    return lock_root / "scans" / f"{digest}.lock"

