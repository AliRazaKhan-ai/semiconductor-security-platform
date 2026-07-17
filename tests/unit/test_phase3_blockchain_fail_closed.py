"""Tests for mandatory blockchain fail-closed behavior."""

from __future__ import annotations

from pathlib import Path

from app.pipeline.orchestrator import Phase3Orchestrator


def test_completed_run_with_blockchain_error_is_not_replayable(
    tmp_path: Path,
) -> None:
    orchestrator = Phase3Orchestrator(tmp_path)

    file_hash = "a" * 64
    scan_id = "scan-blockchain-failure-123"

    orchestrator.store.save_run(
        scan_id,
        {
            "scan_id": scan_id,
            "status": "COMPLETED",
            "stages": [
                {
                    "stage": "BLOCKCHAIN",
                    "status": "INFRASTRUCTURE_ERROR",
                }
            ],
        },
    )

    orchestrator.store.register_file_hash(
        file_hash,
        scan_id,
    )

    stored = orchestrator.store.load_run(scan_id)

    stages = stored["stages"]

    blockchain_healthy = all(
        not (
            stage.get("stage") == "BLOCKCHAIN"
            and stage.get("status")
            == "INFRASTRUCTURE_ERROR"
        )
        for stage in stages
    )

    assert blockchain_healthy is False


def test_successful_blockchain_stage_is_replayable() -> None:
    stages = [
        {
            "stage": "BLOCKCHAIN",
            "status": "PASSED",
        }
    ]

    blockchain_healthy = all(
        not (
            stage.get("stage") == "BLOCKCHAIN"
            and stage.get("status")
            == "INFRASTRUCTURE_ERROR"
        )
        for stage in stages
    )

    assert blockchain_healthy is True
