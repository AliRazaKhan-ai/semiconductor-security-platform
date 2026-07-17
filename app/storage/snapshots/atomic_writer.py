"""Purpose: Persist JSON snapshots through atomic replace and optional fsync.
Directory: app/storage/snapshots.
Dependencies: json, os, tempfile, pathlib.
Connection: Used by snapshot and index builders to avoid partial files.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, value: Any, *, fsync: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            stream.write("\n")
            stream.flush()
            if fsync:
                os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        if fsync:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)

