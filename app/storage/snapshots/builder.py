"""Purpose: Build latest-state JSON projections from immutable scan events.
Directory: app/storage/snapshots.
Dependencies: EventRecord, atomic writer.
Connection: EventWriter updates snapshots; REST query routes read them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.storage.event_store.locking import FileLock
from app.storage.event_store.schemas import EventRecord
from app.storage.snapshots.atomic_writer import atomic_write_json


class SnapshotBuilder:
    def __init__(self, root: Path, lock_root: Path, *, fsync: bool = True) -> None:
        self.root = root
        self.lock_root = lock_root
        self.fsync = fsync

    def path_for(self, scan_id: str) -> Path:
        return self.root / "scans" / f"{scan_id}.json"

    def update(self, event: EventRecord, event_count: int) -> dict[str, Any]:
        path = self.path_for(event.scan_id)
        lock_path = self.lock_root / "snapshots" / f"{event.scan_id}.lock"
        snapshot = {
            "scan_id": event.scan_id,
            "chip_id": event.chip_id,
            "status": str(event.payload.get("status", "UNKNOWN")),
            "current_stage": event.pipeline_stage,
            "last_event_type": event.event_type,
            "last_event_id": event.event_id,
            "last_event_hash": event.event_hash,
            "last_sequence": event.sequence,
            "event_count": event_count,
            "updated_at": event.timestamp_utc,
            "correlation_id": event.correlation_id,
            "latest_payload": event.payload,
            "schema_version": event.schema_version,
        }
        with FileLock(lock_path):
            atomic_write_json(path, snapshot, fsync=self.fsync)
        return snapshot

