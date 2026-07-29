"""Purpose: Publish durable event-store records to read-only SocketIO clients.
Directory: app/websocket.
Dependencies: Flask-SocketIO, SocketEvent.
Connection: REST and future pipeline stages call this only after successful persistence.
"""

from __future__ import annotations

from flask_socketio import SocketIO

from app.storage.event_store.schemas import EventRecord
from app.websocket.schemas import SocketEvent


class SocketPublisher:
    def __init__(self, socketio: SocketIO, namespace: str) -> None:
        self.socketio = socketio
        self.namespace = namespace

    def publish_record(self, record: EventRecord) -> None:
        payload = SocketEvent.from_record(record).to_dict()
        # Omitting ``to`` broadcasts to every connected client in the
        # namespace. Broadcasting through a named room depends on every client joining
        # a room named "all" and can silently lose events during reconnects.
        self.socketio.emit(
            "platform.event",
            payload,
            namespace=self.namespace,
        )
        self.socketio.emit(
            "platform.event",
            payload,
            namespace=self.namespace,
            to=f"scan:{record.scan_id}",
        )
        if record.event_type.startswith("system."):
            self.socketio.emit("platform.event", payload, namespace=self.namespace, to="system")

