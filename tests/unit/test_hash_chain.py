from __future__ import annotations

from dataclasses import replace

from app.storage.event_store.hash_chain import seal_event, verify_chain
from app.storage.event_store.schemas import EventRecord


def test_hash_chain_detects_mutation() -> None:
    first = seal_event(
        EventRecord.new(
            scan_id="scan-1",
            chip_id="chip-1",
            sequence=1,
            event_type="scan.accepted",
            pipeline_stage="INGESTION",
            correlation_id="correlation-1",
            source_component="test",
            component_version="1.0.0",
            payload={"status": "RECEIVED"},
        )
    )
    second = seal_event(
        EventRecord.new(
            scan_id="scan-1",
            chip_id="chip-1",
            sequence=2,
            event_type="stage.started",
            pipeline_stage="PUF",
            correlation_id="correlation-1",
            source_component="test",
            component_version="1.0.0",
            payload={"status": "PROCESSING"},
            previous_event_hash=first.event_hash,
        )
    )
    assert verify_chain([first, second])[0] is True
    altered = replace(second, payload={"status": "APPROVED"})
    assert verify_chain([first, altered])[0] is False

