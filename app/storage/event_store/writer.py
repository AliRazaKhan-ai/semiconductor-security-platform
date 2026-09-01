"""Purpose: Append immutable, hash-chained JSONL scan events durably.
Directory: app/storage/event_store.
Dependencies: os, json, event hashing, locks, indexes, snapshots.
Connection: REST and pipeline services persist every state transition through this writer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.exceptions import ConflictError, EventStoreError
from app.storage.event_store.hash_chain import seal_event
from app.storage.event_store.locking import FileLock
from app.storage.event_store.partitioning import (
    scan_event_path,
    scan_lock_path,
    validate_identifier,
)
from app.storage.event_store.schemas import EventRecord
from app.storage.indexes.builder import IndexBuilder
from app.storage.indexes.reader import IndexReader
from app.storage.snapshots.builder import SnapshotBuilder


class EventWriter:
    def __init__(
        self,
        *,
        event_store_root: Path,
        index_root: Path,
        snapshot_root: Path,
        lock_root: Path,
        fsync: bool = True,
        maximum_event_bytes: int = 1_048_576,
    ) -> None:
        self.event_store_root = event_store_root
        self.index_root = index_root
        self.snapshot_root = snapshot_root
        self.lock_root = lock_root
        self.fsync = fsync
        self.maximum_event_bytes = maximum_event_bytes
        self.index_builder = IndexBuilder(index_root, lock_root, fsync=fsync)
        self.index_reader = IndexReader(index_root, event_store_root)
        self.snapshot_builder = SnapshotBuilder(snapshot_root, lock_root, fsync=fsync)

    @staticmethod
    def _read_last_event(path: Path) -> EventRecord | None:
        if not path.exists() or path.stat().st_size == 0:
            return None
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            position = end - 1
            while position >= 0:
                stream.seek(position)
                if stream.read(1) == b"\n" and position < end - 1:
                    stream.seek(position + 1)
                    break
                position -= 1
            else:
                stream.seek(0)
            line = stream.readline().decode("utf-8").strip()
        return EventRecord.from_dict(json.loads(line)) if line else None

    def append(
        self,
        *,
        scan_id: str,
        chip_id: str,
        event_type: str,
        pipeline_stage: str,
        correlation_id: str,
        source_component: str,
        component_version: str,
        payload: dict[str, Any] | None = None,
        evidence_hashes: dict[str, str] | None = None,
        reject_existing_scan: bool = False,
    ) -> EventRecord:
        validate_identifier(scan_id, "scan_id")
        validate_identifier(chip_id, "chip_id")
        lock_path = scan_lock_path(self.lock_root, scan_id)

        with FileLock(lock_path):
            existing_path = self._locate_existing(scan_id)
            if reject_existing_scan and existing_path is not None:
                raise ConflictError("Scan identifier already exists", {"scan_id": scan_id})
            path = existing_path or scan_event_path(self.event_store_root, scan_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            last = self._read_last_event(path)
            sequence = 1 if last is None else last.sequence + 1
            previous_hash = "" if last is None else last.event_hash
            event = EventRecord.new(
                scan_id=scan_id,
                chip_id=chip_id,
                sequence=sequence,
                event_type=event_type,
                pipeline_stage=pipeline_stage,
                correlation_id=correlation_id,
                source_component=source_component,
                component_version=component_version,
                payload=payload,
                evidence_hashes=evidence_hashes,
                previous_event_hash=previous_hash,
            )
            event = seal_event(event)
            line = json.dumps(
                event.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
                default=str,
            ).encode("utf-8") + b"\n"
            if len(line) > self.maximum_event_bytes:
                raise EventStoreError(
                    "Event exceeds configured maximum size",
                    {"bytes": len(line), "maximum": self.maximum_event_bytes},
                )
            descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o640)
            try:
                written = os.write(descriptor, line)
                if written != len(line):
                    raise EventStoreError("Incomplete event journal write")
                if self.fsync:
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)

        self.index_builder.update(event, path, self.event_store_root)
        self.snapshot_builder.update(event, sequence)
        return event

    def _locate_existing(self, scan_id: str) -> Path | None:
        indexed = self.index_reader.scan_path(scan_id)
        if indexed is not None and indexed.exists():
            return indexed
        matches = list(self.event_store_root.rglob(f"{scan_id}.jsonl"))
        if len(matches) > 1:
            raise EventStoreError("Duplicate scan journals detected", {"scan_id": scan_id})
        return matches[0] if matches else None

