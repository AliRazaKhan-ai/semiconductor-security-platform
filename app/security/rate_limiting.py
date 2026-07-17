"""Purpose: Enforce bounded in-memory request rates without user accounts.
Directory: app/security.
Dependencies: threading, time, collections.
Connection: Called by request hooks before REST endpoints execute.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.exceptions import RateLimitError


class RateLimiter:
    def __init__(self, *, requests: int, window_seconds: int) -> None:
        if requests <= 0 or window_seconds <= 0:
            raise ValueError("Rate limit values must be positive")
        self.requests = requests
        self.window_seconds = window_seconds
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int | None = None) -> None:
        current = time.monotonic()
        threshold = current - self.window_seconds
        effective_limit = limit or self.requests
        with self._lock:
            timestamps = self._entries[key]
            while timestamps and timestamps[0] <= threshold:
                timestamps.popleft()
            if len(timestamps) >= effective_limit:
                retry_after = max(1, int(self.window_seconds - (current - timestamps[0])))
                raise RateLimitError(retry_after)
            timestamps.append(current)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

