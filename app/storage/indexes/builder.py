"""Purpose: Maintain rebuildable scan, chip, status, and latest indexes.
Directory: app/storage/indexes.
Dependencies: FileLock, atomic JSON writer, EventRecord.
Connection: Called after each durable event append.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.storage.event_store.locking import FileLock
from app.storage.event_store.schemas import EventRecord
from app.storage.snapshots.atomic_writer import atomic_write_json


class IndexBuilder:
    def __init__(self, root: Path, lock_root: Path, *, fsync: bool = True) -> None:
        self.root = root
        self.lock_root = lock_root
        self.fsync = fsync

    def _read(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def update(self, event: EventRecord, journal_path: Path, event_store_root: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(self.lock_root / "indexes" / "global.lock"):
            scan_index = self._read("scan_index.json", {})
            chip_index = self._read("chip_index.json", {})
            status_index = self._read("status_index.json", {})
            latest_index = self._read("latest.json", [])

            relative_path = str(journal_path.relative_to(event_store_root))
            scan_index[event.scan_id] = {
                "path": relative_path,
                "chip_id": event.chip_id,
                "last_sequence": event.sequence,
                "last_event_type": event.event_type,
                "updated_at": event.timestamp_utc,
                "status": event.payload.get("status", "UNKNOWN"),
            }

            scan_ids = list(chip_index.get(event.chip_id, []))
            if event.scan_id not in scan_ids:
                scan_ids.append(event.scan_id)
            chip_index[event.chip_id] = scan_ids

            status = str(event.payload.get("status", "UNKNOWN"))
            for status_name, members in list(status_index.items()):
                if event.scan_id in members and status_name != status:
                    status_index[status_name] = [item for item in members if item != event.scan_id]
            members = list(status_index.get(status, []))
            if event.scan_id not in members:
                members.append(event.scan_id)
            status_index[status] = members

            latest_index = [item for item in latest_index if item.get("scan_id") != event.scan_id]
            latest_index.insert(
                0,
                {
                    "scan_id": event.scan_id,
                    "chip_id": event.chip_id,
                    "updated_at": event.timestamp_utc,
                    "status": status,
                },
            )
            latest_index = latest_index[:1000]

            atomic_write_json(self.root / "scan_index.json", scan_index, fsync=self.fsync)
            atomic_write_json(self.root / "chip_index.json", chip_index, fsync=self.fsync)
            atomic_write_json(self.root / "status_index.json", status_index, fsync=self.fsync)
            atomic_write_json(self.root / "latest.json", latest_index, fsync=self.fsync)

