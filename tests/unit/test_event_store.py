from __future__ import annotations

from pathlib import Path

import pytest

from app.exceptions import ConflictError
from app.storage.event_store import EventStore


def make_store(root: Path) -> EventStore:
    return EventStore(
        event_store_root=root / "events",
        index_root=root / "indexes",
        snapshot_root=root / "snapshots",
        lock_root=root / "locks",
    )


def test_event_store_appends_and_verifies(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = store.append(
        scan_id="scan-1",
        chip_id="chip-1",
        event_type="scan.accepted",
        pipeline_stage="INGESTION",
        correlation_id="c-1",
        source_component="test",
        component_version="1.0.0",
        payload={"status": "RECEIVED"},
        reject_existing_scan=True,
    )
    second = store.append(
        scan_id="scan-1",
        chip_id="chip-1",
        event_type="stage.started",
        pipeline_stage="PUF",
        correlation_id="c-1",
        source_component="test",
        component_version="1.0.0",
        payload={"status": "PROCESSING"},
    )
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_event_hash == first.event_hash
    assert len(store.events("scan-1")) == 2
    assert store.snapshot("scan-1")["status"] == "PROCESSING"
    assert store.verify_all().valid is True


def test_event_store_rejects_duplicate_initial_scan(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    arguments = {
        "scan_id": "scan-1",
        "chip_id": "chip-1",
        "event_type": "scan.accepted",
        "pipeline_stage": "INGESTION",
        "correlation_id": "c-1",
        "source_component": "test",
        "component_version": "1.0.0",
        "payload": {"status": "RECEIVED"},
        "reject_existing_scan": True,
    }
    store.append(**arguments)
    with pytest.raises(ConflictError):
        store.append(**arguments)

