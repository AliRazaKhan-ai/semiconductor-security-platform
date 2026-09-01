"""Tests for terminal-to-dashboard integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import create_app
from app.integration import IntegratedPipelineService


def _real_hardware_manifest_available(path: Path) -> bool:
    """Return true only when every declared hardware evidence file exists."""
    simulation = json.loads(path.read_text(encoding="utf-8"))

    manifest = (
        simulation.get("hardware_manifest")
        or simulation.get("manifest")
        or (
            simulation.get("hardware_security", {}).get("manifest")
            if isinstance(simulation.get("hardware_security"), dict)
            else None
        )
    )

    if not isinstance(manifest, dict):
        return False

    required_paths = (
        "opentitan_evidence",
        "side_channel_trace",
        "side_channel_reference",
        "ai_em_trace",
        "ai_timing_trace",
        "rtl_file",
        "testbench_file",
    )

    for field in required_paths:
        value = manifest.get(field)

        if not value:
            return False

        evidence_path = Path(str(value)).expanduser()

        if not evidence_path.is_absolute():
            evidence_path = Path.cwd() / evidence_path

        if not evidence_path.exists():
            return False

    artifacts = manifest.get("sbom_artifacts")

    if not isinstance(artifacts, list) or not artifacts:
        return False

    for value in artifacts:
        artifact = Path(str(value)).expanduser()

        if not artifact.is_absolute():
            artifact = Path.cwd() / artifact

        if not artifact.exists():
            return False

    return all(
        str(manifest.get(field) or "").strip()
        for field in (
            "top_module",
            "puf_identity_hash",
            "twin_id",
        )
    )

def test_integrated_pipeline_is_registered() -> None:
    app = create_app()

    service = app.extensions.get(
        "semisecure.integrated_pipeline"
    )

    assert isinstance(
        service,
        IntegratedPipelineService,
    )


def test_integration_routes_are_registered() -> None:
    app = create_app()
    routes = {
        str(rule)
        for rule in app.url_map.iter_rules()
    }

    assert "/api/v1/integration/run" in routes
    assert "/api/v1/integration/runs" in routes
    assert (
        "/api/v1/integration/runs/<identifier>"
        in routes
    )


def test_good_chip_complete_integration() -> None:
    chip_path = Path("data/chips/chip_01_good.json")

    if not _real_hardware_manifest_available(chip_path):
        pytest.skip(
            "Real hardware evidence manifest is not available for the good chip"
        )

    app = create_app()

    service = app.extensions[
        "semisecure.integrated_pipeline"
    ]

    result = service.run_file(
        Path(
            "data/chips/chip_01_good.json"
        ),
        force=True,
    )

    run = result["run"]

    assert run["status"] == "COMPLETED"
    assert run["deployment_decision"] == "DEPLOY"
    assert run["quarantined"] is False

    stages = {
        stage["stage"]: stage
        for stage in run["stages"]
    }

    assert stages["INGESTION"]["status"] == "PASSED"
    assert (
        stages["PUF_AUTHENTICATION"]["status"]
        == "PASSED"
    )
    assert (
        stages["HARDWARE_SECURITY"]["status"]
        == "PASSED"
    )
    assert stages["AI_ANALYSIS"]["status"] == "PASSED"
    assert stages["COMPLIANCE"]["status"] == "PASSED"
    assert stages["BLOCKCHAIN"]["status"] == "PASSED"
    assert stages["DASHBOARD"]["status"] == "PASSED"
    assert (
        stages["DEPLOYMENT_DECISION"]["status"]
        == "PASSED"
    )


def test_weak_puf_stops_before_hardware_ai_and_compliance() -> None:
    app = create_app()

    service = app.extensions[
        "semisecure.integrated_pipeline"
    ]

    result = service.run_file(
        Path(
            "data/chips/chip_03_puf_unstable.json"
        ),
        force=True,
    )

    run = result["run"]

    assert run["status"] == "STOPPED"
    assert (
        run["stopped_stage"]
        == "PUF_AUTHENTICATION"
    )
    assert run["quarantined"] is True

    stage_names = [
        stage["stage"]
        for stage in run["stages"]
    ]

    assert "PUF_AUTHENTICATION" in stage_names
    assert "HARDWARE_SECURITY" not in stage_names
    assert "AI_ANALYSIS" not in stage_names
    assert "COMPLIANCE" not in stage_names
    assert "BLOCKCHAIN" not in stage_names
