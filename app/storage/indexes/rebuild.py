"""Purpose: Reconstruct all JSON indexes from authoritative event journals.
Directory: app/storage/indexes.
Dependencies: EventRecord, IndexBuilder.
Connection: Used during recovery after index loss or corruption.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.storage.event_store.schemas import EventRecord
from app.storage.indexes.builder import IndexBuilder


def rebuild_indexes(
    event_store_root: Path,
    index_root: Path,
    lock_root: Path,
    *,
    fsync: bool = True,
) -> int:
    for name in ("scan_index.json", "chip_index.json", "status_index.json", "latest.json"):
        (index_root / name).unlink(missing_ok=True)
    builder = IndexBuilder(index_root, lock_root, fsync=fsync)
    count = 0
    for path in sorted(event_store_root.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                builder.update(EventRecord.from_dict(value), path, event_store_root)
                count += 1
    return count

