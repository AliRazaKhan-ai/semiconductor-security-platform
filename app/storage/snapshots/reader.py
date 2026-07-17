"""Purpose: Read latest-state JSON scan projections.
Directory: app/storage/snapshots.
Dependencies: json, pathlib.
Connection: Used by REST and system-status queries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, scan_id: str) -> Path:
        return self.root / "scans" / f"{scan_id}.json"

    def get(self, scan_id: str) -> dict[str, Any] | None:
        path = self.path_for(scan_id)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None

    def list_latest(self, limit: int = 50) -> list[dict[str, Any]]:
        directory = self.root / "scans"
        if not directory.exists():
            return []
        paths = sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        results: list[dict[str, Any]] = []
        for path in paths[:limit]:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                results.append(value)
        return results

