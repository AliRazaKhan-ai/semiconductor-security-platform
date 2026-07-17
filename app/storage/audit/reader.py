"""Purpose: Read audit records for operational review.
Directory: app/storage/audit.
Dependencies: json, pathlib.
Connection: System status and future compliance reporting consume this reader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        paths = sorted(self.root.rglob("audit-*.jsonl"), reverse=True)
        records: list[dict[str, Any]] = []
        for path in paths:
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        records.append(value)
                if len(records) >= limit:
                    return records
        return records

