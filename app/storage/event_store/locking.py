"""Purpose: Provide process-safe advisory file locks on Ubuntu.
Directory: app/storage/event_store.
Dependencies: fcntl, pathlib.
Connection: Serialises event, index, snapshot, and audit writers.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType


class FileLock:
    def __init__(self, path: Path, exclusive: bool = True) -> None:
        self.path = path
        self.exclusive = exclusive
        self._descriptor: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o640)
        operation = fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
        fcntl.flock(self._descriptor, operation)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None

