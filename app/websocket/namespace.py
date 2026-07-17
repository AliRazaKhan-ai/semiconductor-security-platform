"""Purpose: Implement the read-only SocketIO namespace.
Directory: app/websocket.
Dependencies: Flask-SocketIO Namespace, rooms, EventStore replay.
Connection: Registered by app.factory; permits subscriptions and replay but no state mutation.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import request
from flask_socketio import Namespace, emit, join_room, leave_room

from app.exceptions import PlatformError, ValidationError
from app.websocket.connection_manager import ConnectionManager
from app.websocket.replay import ReplayService
from app.websocket.schemas import server_message
from app.websocket.subscriptions import room_for

logger = logging.getLogger(__name__)


class ReadOnlyEventNamespace(Namespace):
    def __init__(
        self,
        namespace: str,
        connection_manager: ConnectionManager,
        replay_service: ReplayService,
        application_version: str,
    ) -> None:
        super().__init__(namespace)
        self.connection_manager = connection_manager
        self.replay_service = replay_service
        self.application_version = application_version

    def on_connect(self, auth: Any = None) -> None:
        del auth
        self.connection_manager.connect(request.sid)
        join_room("all")
        self.connection_manager.add_room(request.sid, "all")
        emit(
            "server.ready",
            server_message(
                "server.ready",
                {
                    "sid": request.sid,
                    "namespace": self.namespace,
                    "application_version": self.application_version,
                    "mode": "read_only",
                },
            ),
        )
        logger.info("socket_connected", extra={"sid": request.sid, "namespace": self.namespace})

    def on_disconnect(self, reason: str | None = None) -> None:
        self.connection_manager.disconnect(request.sid)
        logger.info(
            "socket_disconnected",
            extra={"sid": request.sid, "namespace": self.namespace, "reason": reason},
        )

    def on_subscribe(self, data: Any) -> dict[str, Any]:
        try:
            room = room_for(data)
            join_room(room)
            self.connection_manager.add_room(request.sid, room)
            response = server_message("subscription.accepted", {"room": room})
            emit("subscription.accepted", response)
            return response
        except PlatformError as exc:
            response = server_message(
                "subscription.rejected",
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
            emit("subscription.rejected", response)
            return response

    def on_unsubscribe(self, data: Any) -> dict[str, Any]:
        try:
            room = room_for(data)
            if room == "all":
                raise ValidationError("The default all-events room cannot be removed")
            leave_room(room)
            self.connection_manager.remove_room(request.sid, room)
            response = server_message("subscription.removed", {"room": room})
            emit("subscription.removed", response)
            return response
        except PlatformError as exc:
            response = server_message(
                "subscription.rejected",
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
            emit("subscription.rejected", response)
            return response

    def on_replay(self, data: Any) -> dict[str, Any]:
        try:
            if not isinstance(data, dict):
                raise ValidationError("Replay request must be a JSON object")
            scan_id = data.get("scan_id")
            if not isinstance(scan_id, str) or not scan_id.strip():
                raise ValidationError("scan_id is required")
            after_sequence_raw = data.get("after_sequence", 0)
            if not isinstance(after_sequence_raw, int) or after_sequence_raw < 0:
                raise ValidationError("after_sequence must be a non-negative integer")
            events = self.replay_service.replay(scan_id.strip(), after_sequence_raw)
            response = server_message(
                "replay.batch",
                {
                    "scan_id": scan_id.strip(),
                    "after_sequence": after_sequence_raw,
                    "count": len(events),
                    "events": events,
                },
            )
            emit("replay.batch", response)
            return response
        except PlatformError as exc:
            response = server_message(
                "replay.failed",
                {"code": exc.code, "message": exc.message, "details": exc.details},
            )
            emit("replay.failed", response)
            return response

