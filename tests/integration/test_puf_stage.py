"""Integration tests for terminal PUF evidence, JSON Event Store, and SocketIO publication contract."""

from __future__ import annotations

from pathlib import Path

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.config import load_puf_config
from tests.puf_test_config import compact_puf_config
from app.pipeline.stages.puf_stage import PUFStage
from app.storage.event_store import EventStore


class RecordingPublisher:
    def __init__(self) -> None:
        self.records = []

    def publish_record(self, record) -> None:
        self.records.append(record)


def _components(tmp_path: Path):
    adapter = PUFAdapter(
        config=compact_puf_config(),
        master_secret=b"integration-master-secret-000000000000000000000000000",
        project_root=tmp_path,
    )
    store = EventStore(
        event_store_root=tmp_path / "data" / "event_store",
        index_root=tmp_path / "data" / "indexes",
        snapshot_root=tmp_path / "data" / "snapshots",
        lock_root=tmp_path / "runtime" / "locks",
        fsync=False,
        verify_on_read=True,
    )
    publisher = RecordingPublisher()
    stage = PUFStage(adapter=adapter, event_store=store, publisher=publisher)
    return adapter, store, publisher, stage


def test_puf_stage_persists_and_publishes_success(tmp_path: Path) -> None:
    adapter, store, publisher, stage = _components(tmp_path)
    chip_id = "CHIP-STAGE-GOOD"
    adapter.enroll_device(chip_id)
    challenge = adapter.issue_challenge(chip_id)
    response = adapter.simulate_response(chip_id, challenge)

    outcome = stage.execute(
        scan_id="scan-puf-good",
        chip_id=chip_id,
        correlation_id="corr-puf-good",
        evidence={"puf": {"challenge": challenge.to_dict(), "response": response.to_dict()}},
    )

    assert outcome.passed
    events = store.events("scan-puf-good")
    assert [event.event_type for event in events] == ["stage.started", "stage.completed"]
    assert events[-1].payload["stop_pipeline"] is False
    assert events[-1].evidence_hashes["puf_identity"]
    assert len(publisher.records) == 2


def test_puf_stage_fails_closed_for_clone(tmp_path: Path) -> None:
    adapter, store, publisher, stage = _components(tmp_path)
    chip_id = "CHIP-STAGE-TARGET"
    adapter.enroll_device(chip_id)
    challenge = adapter.issue_challenge(chip_id)
    clone_response = adapter.simulator("CHIP-STAGE-CLONE").respond(
        challenge,
        sample_count=adapter.config.authentication.response_samples,
    )

    outcome = stage.execute(
        scan_id="scan-puf-clone",
        chip_id=chip_id,
        correlation_id="corr-puf-clone",
        evidence={"puf": {"challenge": challenge.to_dict(), "response": clone_response.to_dict()}},
    )

    assert not outcome.passed
    events = store.events("scan-puf-clone")
    assert events[-1].event_type == "stage.failed"
    assert events[-1].payload["stop_pipeline"] is True
    assert len(publisher.records) == 2


def test_puf_stage_fails_closed_when_terminal_evidence_is_missing(tmp_path: Path) -> None:
    _, store, _, stage = _components(tmp_path)
    outcome = stage.execute(
        scan_id="scan-puf-missing",
        chip_id="CHIP-MISSING-EVIDENCE",
        correlation_id="corr-puf-missing",
        evidence={},
    )

    assert not outcome.passed
    assert outcome.status == "FAILED_CLOSED"
    assert store.events("scan-puf-missing")[-1].payload["stop_pipeline"] is True
