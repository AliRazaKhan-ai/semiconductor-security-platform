"""Purpose: Provide the application-facing JSON event-store facade.
Directory: app/storage/event_store.
Dependencies: reader, writer, recovery.
Connection: Stored in Flask app.extensions and used by API, SocketIO, and health modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.storage.event_store.reader import EventReader
from app.storage.event_store.recovery import EventStoreRecovery
from app.storage.event_store.schemas import EventRecord, VerificationReport
from app.storage.event_store.writer import EventWriter


class EventStore:
    def __init__(
        self,
        *,
        event_store_root: Path,
        index_root: Path,
        snapshot_root: Path,
        lock_root: Path,
        fsync: bool = True,
        verify_on_read: bool = True,
        maximum_event_bytes: int = 1_048_576,
    ) -> None:
        for path in (event_store_root, index_root, snapshot_root, lock_root):
            path.mkdir(parents=True, exist_ok=True)
        self.writer = EventWriter(
            event_store_root=event_store_root,
            index_root=index_root,
            snapshot_root=snapshot_root,
            lock_root=lock_root,
            fsync=fsync,
            maximum_event_bytes=maximum_event_bytes,
        )
        self.reader = EventReader(
            event_store_root=event_store_root,
            index_root=index_root,
            snapshot_root=snapshot_root,
            verify_on_read=verify_on_read,
        )
        self.recovery = EventStoreRecovery(
            event_store_root=event_store_root,
            index_root=index_root,
            snapshot_root=snapshot_root,
            lock_root=lock_root,
            fsync=fsync,
        )

    def append(self, **kwargs: Any) -> EventRecord:
        return self.writer.append(**kwargs)

    def events(self, scan_id: str, **kwargs: Any) -> list[EventRecord]:
        return self.reader.events(scan_id, **kwargs)

    def snapshot(self, scan_id: str) -> dict[str, Any]:
        return self.reader.snapshot(scan_id)

    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.reader.latest(limit)

    def chip_history(self, chip_id: str, limit: int = 500) -> list[dict[str, Any]]:
        return self.reader.chip_history(chip_id, limit=limit)

    def count_scans(self) -> int:
        return self.reader.count_scans()

    def verify_all(self) -> VerificationReport:
        return self.recovery.verify_all()

    def rebuild(self) -> VerificationReport:
        return self.recovery.rebuild()


__all__ = ["EventRecord", "EventStore", "VerificationReport"]

