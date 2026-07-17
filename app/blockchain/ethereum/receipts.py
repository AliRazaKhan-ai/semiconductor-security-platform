"""Durable local Ethereum receipt repository using atomic JSON files."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.blockchain.common.hashing import require_sha256


class ReceiptRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, root_hash: str) -> Path:
        return self.root / f"{require_sha256(root_hash, field='root_hash')}.json"

    def put(self, root_hash: str, receipt: dict[str, Any]) -> None:
        destination = self._path(root_hash)
        if destination.exists():
            existing = json.loads(destination.read_text(encoding="utf-8"))
            if existing != receipt:
                raise RuntimeError("an immutable Ethereum receipt already exists for this root")
            return
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as stream:
            json.dump(receipt, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        temporary.replace(destination)

    def get(self, root_hash: str) -> dict[str, Any] | None:
        path = self._path(root_hash)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
