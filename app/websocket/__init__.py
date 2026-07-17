"""Purpose: Initialise read-only Flask-SocketIO services.
Directory: app/websocket.
Dependencies: SocketIO, EventStore, namespace, publisher.
Connection: app.factory registers one namespace and stores publisher and manager extensions.
"""

from __future__ import annotations

from flask_socketio import SocketIO

from app.storage.event_store import EventStore
from app.websocket.connection_manager import ConnectionManager
from app.websocket.namespace import ReadOnlyEventNamespace
from app.websocket.publisher import SocketPublisher
from app.websocket.replay import ReplayService


def initialise_websocket(
    *,
    socketio: SocketIO,
    event_store: EventStore,
    namespace: str,
    maximum_replay_events: int,
    application_version: str,
) -> tuple[ConnectionManager, SocketPublisher]:
    manager = ConnectionManager()
    replay = ReplayService(event_store, maximum_replay_events)
    socketio.on_namespace(
        ReadOnlyEventNamespace(namespace, manager, replay, application_version)
    )
    return manager, SocketPublisher(socketio, namespace)


__all__ = ["initialise_websocket"]

