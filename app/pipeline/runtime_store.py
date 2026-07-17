"""Atomic persistence for Phase 3 pipeline runs and quarantine records."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class PipelineRuntimeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.runs_root = self.root / "data" / "pipeline_runs"
        self.quarantine_root = self.root / "data" / "quarantine"
        self.index_path = self.runs_root / "index.json"
        self.lock_path = self.runs_root / ".lock"

        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)

        if not self.index_path.exists():
            self._atomic_write(
                self.index_path,
                {
                    "schema_version": "1.0",
                    "files": {},
                },
            )

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with self.lock_path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic_write(
        path: Path,
        value: dict[str, Any] | list[Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(
                value,
                temporary,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)

        os.replace(temporary_path, path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)

        value = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(value, dict):
            raise ValueError(
                f"Expected JSON object in {path}"
            )

        return value

    def run_path(self, scan_id: str) -> Path:
        return self.runs_root / scan_id / "run.json"

    def save_run(
        self,
        scan_id: str,
        value: dict[str, Any],
    ) -> None:
        with self._lock():
            self._atomic_write(self.run_path(scan_id), value)

    def load_run(self, scan_id: str) -> dict[str, Any]:
        return self._read(self.run_path(scan_id))

    def find_by_file_hash(
        self,
        file_hash: str,
    ) -> str | None:
        with self._lock():
            index = self._read(self.index_path)
            files = index.get("files", {})

            if not isinstance(files, dict):
                return None

            value = files.get(file_hash)

            return str(value) if value else None

    def register_file_hash(
        self,
        file_hash: str,
        scan_id: str,
    ) -> None:
        with self._lock():
            index = self._read(self.index_path)
            files = index.setdefault("files", {})

            if not isinstance(files, dict):
                raise ValueError(
                    "Pipeline run index is malformed"
                )

            files[file_hash] = scan_id
            self._atomic_write(self.index_path, index)

    def quarantine(
        self,
        scan_id: str,
        value: dict[str, Any],
    ) -> Path:
        path = self.quarantine_root / f"{scan_id}.json"

        with self._lock():
            self._atomic_write(path, value)

        return path

    def list_quarantine(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        for path in sorted(self.quarantine_root.glob("*.json")):
            try:
                record = self._read(path)
            except Exception as exc:
                records.append(
                    {
                        "file": str(path),
                        "error": str(exc),
                    }
                )
                continue

            records.append(record)

        return records
