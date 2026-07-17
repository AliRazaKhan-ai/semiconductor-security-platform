"""Purpose: Append hash-chained JSON audit records.
Directory: app/storage/audit.
Dependencies: json, os, FileLock, audit integrity.
Connection: Request hooks and error handlers record security-relevant actions here.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.storage.audit.integrity import audit_hash
from app.storage.event_store.locking import FileLock


class AuditWriter:
    def __init__(self, root: Path, lock_root: Path, *, fsync: bool = True) -> None:
        self.root = root
        self.lock_root = lock_root
        self.fsync = fsync

    def _path(self) -> Path:
        now = datetime.now(UTC)
        return self.root / f"{now.year:04d}" / f"{now.month:02d}" / f"audit-{now.day:02d}.jsonl"

    @staticmethod
    def _last_hash(path: Path) -> str:
        if not path.exists():
            return ""
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return ""
        value = json.loads(lines[-1])
        return str(value.get("record_hash", "")) if isinstance(value, dict) else ""

    def write(self, event_type: str, correlation_id: str, details: dict[str, Any]) -> dict[str, Any]:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self.lock_root / "audit" / "audit.lock"):
            record: dict[str, Any] = {
                "record_id": str(uuid4()),
                "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "event_type": event_type,
                "correlation_id": correlation_id,
                "details": details,
                "previous_record_hash": self._last_hash(path),
                "record_hash": "",
            }
            record["record_hash"] = audit_hash(record)
            line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8") + b"\n"
            descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o640)
            try:
                os.write(descriptor, line)
                if self.fsync:
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return record

