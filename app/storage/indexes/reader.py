"""Purpose: Query rebuildable JSON indexes.
Directory: app/storage/indexes.
Dependencies: json, pathlib.
Connection: Resolves scan journals and chip histories for REST queries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class IndexReader:
    def __init__(self, root: Path, event_store_root: Path) -> None:
        self.root = root
        self.event_store_root = event_store_root

    def _read(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def scan_path(self, scan_id: str) -> Path | None:
        record = self._read("scan_index.json", {}).get(scan_id)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            return None
        path = (self.event_store_root / record["path"]).resolve()
        if self.event_store_root.resolve() not in path.parents:
            return None
        return path

    def scan_metadata(self, scan_id: str) -> dict[str, Any] | None:
        value = self._read("scan_index.json", {}).get(scan_id)
        return value if isinstance(value, dict) else None

    def scan_ids_for_chip(self, chip_id: str) -> list[str]:
        value = self._read("chip_index.json", {}).get(chip_id, [])
        return [str(item) for item in value] if isinstance(value, list) else []

    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        value = self._read("latest.json", [])
        if not isinstance(value, list):
            return []
        return [item for item in value[:limit] if isinstance(item, dict)]

