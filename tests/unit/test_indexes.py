from __future__ import annotations

from pathlib import Path

from app.storage.event_store import EventStore


def test_indexes_resolve_scan_and_chip(tmp_path: Path) -> None:
    store = EventStore(
        event_store_root=tmp_path / "events",
        index_root=tmp_path / "indexes",
        snapshot_root=tmp_path / "snapshots",
        lock_root=tmp_path / "locks",
    )
    store.append(
        scan_id="scan-1",
        chip_id="chip-1",
        event_type="scan.accepted",
        pipeline_stage="INGESTION",
        correlation_id="c-1",
        source_component="test",
        component_version="1",
        payload={"status": "RECEIVED"},
    )
    assert store.reader.index_reader.scan_path("scan-1") is not None
    assert store.reader.index_reader.scan_ids_for_chip("chip-1") == ["scan-1"]
    assert store.latest(1)[0]["scan_id"] == "scan-1"

