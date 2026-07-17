"""Purpose: Define unbound Flask extensions and backend service accessors.
Directory: app.
Dependencies: Flask-SocketIO, EventStore, AuditWriter.
Connection: The factory initialises these objects and routes retrieve them through app.extensions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from flask import current_app
from flask_socketio import SocketIO

from app.storage.audit import AuditReader, AuditWriter
from app.storage.event_store import EventStore

if TYPE_CHECKING:
    from flask import Flask

socketio = SocketIO()


def event_store() -> EventStore:
    return cast(EventStore, current_app.extensions["semisecure.event_store"])


def audit_writer() -> AuditWriter:
    return cast(AuditWriter, current_app.extensions["semisecure.audit_writer"])


def audit_reader() -> AuditReader:
    return cast(AuditReader, current_app.extensions["semisecure.audit_reader"])


def service(name: str) -> Any:
    return current_app.extensions[f"semisecure.{name}"]

