"""Purpose: Track active SocketIO clients and their read-only subscriptions.
Directory: app/websocket.
Dependencies: threading, dataclasses.
Connection: Namespace updates state; system-status diagnostics can inspect counts.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class Connection:
    sid: str
    rooms: set[str] = field(default_factory=set)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {}
        self._lock = threading.RLock()

    def connect(self, sid: str) -> None:
        with self._lock:
            self._connections[sid] = Connection(sid)

    def disconnect(self, sid: str) -> None:
        with self._lock:
            self._connections.pop(sid, None)

    def add_room(self, sid: str, room: str) -> None:
        with self._lock:
            connection = self._connections.setdefault(sid, Connection(sid))
            connection.rooms.add(room)

    def remove_room(self, sid: str, room: str) -> None:
        with self._lock:
            connection = self._connections.get(sid)
            if connection is not None:
                connection.rooms.discard(room)

    def count(self) -> int:
        with self._lock:
            return len(self._connections)

    def rooms(self, sid: str) -> tuple[str, ...]:
        with self._lock:
            connection = self._connections.get(sid)
            return tuple(sorted(connection.rooms)) if connection is not None else ()

