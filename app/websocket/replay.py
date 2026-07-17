"""Purpose: Replay authoritative JSON events after a client reconnects.
Directory: app/websocket.
Dependencies: EventStore.
Connection: Namespace sends missing sequence ranges while REST remains the source of truth.
"""

from __future__ import annotations

from app.storage.event_store import EventStore
from app.websocket.schemas import SocketEvent


class ReplayService:
    def __init__(self, event_store: EventStore, maximum_events: int = 500) -> None:
        self.event_store = event_store
        self.maximum_events = maximum_events

    def replay(self, scan_id: str, after_sequence: int = 0) -> list[dict[str, object]]:
        if after_sequence < 0:
            after_sequence = 0
        events = self.event_store.events(
            scan_id,
            after_sequence=after_sequence,
            limit=self.maximum_events,
        )
        return [SocketEvent.from_record(event).to_dict() for event in events]

