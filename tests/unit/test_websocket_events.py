from __future__ import annotations

from app.storage.event_store.hash_chain import seal_event
from app.storage.event_store.schemas import EventRecord
from app.websocket.schemas import SocketEvent, validate_subscription


def test_socket_event_matches_durable_event() -> None:
    record = seal_event(
        EventRecord.new(
            scan_id="scan-1",
            chip_id="chip-1",
            sequence=1,
            event_type="scan.accepted",
            pipeline_stage="INGESTION",
            correlation_id="c-1",
            source_component="test",
            component_version="1",
            payload={"status": "RECEIVED"},
        )
    )
    message = SocketEvent.from_record(record).to_dict()
    assert message["event_hash"] == record.event_hash
    assert validate_subscription({"channel": "scan", "scan_id": "scan-1"}) == ("scan", "scan-1")

