from __future__ import annotations

from pathlib import Path

from app.storage.event_store import EventStore


def test_snapshot_is_latest_projection(tmp_path: Path) -> None:
    store = EventStore(
        event_store_root=tmp_path / "events",
        index_root=tmp_path / "indexes",
        snapshot_root=tmp_path / "snapshots",
        lock_root=tmp_path / "locks",
    )
    for event_type, stage, status in (
        ("scan.accepted", "INGESTION", "RECEIVED"),
        ("stage.completed", "PUF", "PROCESSING"),
        ("deployment.approved", "DEPLOYMENT", "APPROVED"),
    ):
        store.append(
            scan_id="scan-1",
            chip_id="chip-1",
            event_type=event_type,
            pipeline_stage=stage,
            correlation_id="c-1",
            source_component="test",
            component_version="1",
            payload={"status": status},
        )
    snapshot = store.snapshot("scan-1")
    assert snapshot["status"] == "APPROVED"
    assert snapshot["event_count"] == 3
    assert snapshot["last_sequence"] == 3

