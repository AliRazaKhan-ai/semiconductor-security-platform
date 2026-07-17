from __future__ import annotations

from pathlib import Path

from app.storage.event_store import EventStore


def test_recovery_rebuilds_deleted_indexes(tmp_path: Path) -> None:
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
    for path in (tmp_path / "indexes").glob("*.json"):
        path.unlink()
    report = store.rebuild()
    assert report.valid is True
    assert store.snapshot("scan-1")["scan_id"] == "scan-1"

