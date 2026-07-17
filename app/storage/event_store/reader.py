"""Purpose: Read and verify immutable scan journals and chip histories.
Directory: app/storage/event_store.
Dependencies: json, indexes, snapshots, hash-chain verification.
Connection: REST, SocketIO replay, health, and recovery consume this reader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.exceptions import IntegrityError, NotFoundError
from app.storage.event_store.hash_chain import verify_chain
from app.storage.event_store.schemas import EventRecord
from app.storage.indexes.reader import IndexReader
from app.storage.snapshots.reader import SnapshotReader


class EventReader:
    def __init__(
        self,
        *,
        event_store_root: Path,
        index_root: Path,
        snapshot_root: Path,
        verify_on_read: bool = True,
    ) -> None:
        self.event_store_root = event_store_root
        self.verify_on_read = verify_on_read
        self.index_reader = IndexReader(index_root, event_store_root)
        self.snapshot_reader = SnapshotReader(snapshot_root)

    def locate(self, scan_id: str) -> Path | None:
        indexed = self.index_reader.scan_path(scan_id)
        if indexed is not None and indexed.exists():
            return indexed
        matches = list(self.event_store_root.rglob(f"{scan_id}.jsonl"))
        return matches[0] if len(matches) == 1 else None

    def events(self, scan_id: str, *, after_sequence: int = 0, limit: int = 500) -> list[EventRecord]:
        path = self.locate(scan_id)
        if path is None:
            raise NotFoundError("Scan was not found", {"scan_id": scan_id})
        records: list[EventRecord] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                record = EventRecord.from_dict(value)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise IntegrityError(
                    "Event journal contains an invalid record",
                    {"scan_id": scan_id, "line": line_number},
                ) from exc
            records.append(record)
        if self.verify_on_read:
            valid, reason, sequence = verify_chain(records)
            if not valid:
                raise IntegrityError(
                    "Event journal integrity verification failed",
                    {"scan_id": scan_id, "sequence": sequence, "reason": reason},
                )
        return [record for record in records if record.sequence > after_sequence][:limit]

    def snapshot(self, scan_id: str) -> dict[str, Any]:
        value = self.snapshot_reader.get(scan_id)
        if value is not None:
            return value
        records = self.events(scan_id)
        last = records[-1]
        return {
            "scan_id": last.scan_id,
            "chip_id": last.chip_id,
            "status": last.payload.get("status", "UNKNOWN"),
            "current_stage": last.pipeline_stage,
            "last_event_type": last.event_type,
            "last_event_id": last.event_id,
            "last_event_hash": last.event_hash,
            "last_sequence": last.sequence,
            "event_count": len(records),
            "updated_at": last.timestamp_utc,
            "correlation_id": last.correlation_id,
            "latest_payload": last.payload,
        }

    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in self.index_reader.latest(limit):
            scan_id = item.get("scan_id")
            if isinstance(scan_id, str):
                try:
                    results.append(self.snapshot(scan_id))
                except NotFoundError:
                    continue
        return results

    def chip_history(self, chip_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for scan_id in self.index_reader.scan_ids_for_chip(chip_id):
            for event in self.events(scan_id, limit=limit):
                results.append(event.to_dict())
        results.sort(key=lambda item: str(item.get("timestamp_utc", "")))
        return results[:limit]

    def count_scans(self) -> int:
        path = self.index_reader.root / "scan_index.json"
        if not path.exists():
            return 0
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return len(value) if isinstance(value, dict) else 0
        except (OSError, json.JSONDecodeError):
            return 0

