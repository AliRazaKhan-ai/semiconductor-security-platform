"""Purpose: Verify journals and rebuild disposable indexes and snapshots.
Directory: app/storage/event_store.
Dependencies: JSON, hash chain, indexes, snapshots.
Connection: Invoked by management command and readiness diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.storage.event_store.hash_chain import verify_chain
from app.storage.event_store.schemas import EventRecord, VerificationIssue, VerificationReport
from app.storage.indexes.rebuild import rebuild_indexes
from app.storage.snapshots.builder import SnapshotBuilder


class EventStoreRecovery:
    def __init__(
        self,
        *,
        event_store_root: Path,
        index_root: Path,
        snapshot_root: Path,
        lock_root: Path,
        fsync: bool = True,
    ) -> None:
        self.event_store_root = event_store_root
        self.index_root = index_root
        self.snapshot_root = snapshot_root
        self.lock_root = lock_root
        self.fsync = fsync

    def verify_all(self) -> VerificationReport:
        issues: list[VerificationIssue] = []
        files_checked = 0
        events_checked = 0
        for path in sorted(self.event_store_root.rglob("*.jsonl")):
            files_checked += 1
            records: list[EventRecord] = []
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    records.append(EventRecord.from_dict(value))
                except Exception as exc:
                    issues.append(VerificationIssue(str(path), line_number, f"invalid JSON event: {exc}"))
            valid, reason, sequence = verify_chain(records)
            if not valid:
                issues.append(VerificationIssue(str(path), sequence, reason))
            events_checked += len(records)
        return VerificationReport(not issues, files_checked, events_checked, tuple(issues))

    def rebuild(self) -> VerificationReport:
        report = self.verify_all()
        if not report.valid:
            return report
        rebuild_indexes(
            self.event_store_root,
            self.index_root,
            self.lock_root,
            fsync=self.fsync,
        )
        builder = SnapshotBuilder(self.snapshot_root, self.lock_root, fsync=self.fsync)
        for path in sorted(self.event_store_root.rglob("*.jsonl")):
            records = [
                EventRecord.from_dict(json.loads(line))
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if records:
                builder.update(records[-1], len(records))
        return report

