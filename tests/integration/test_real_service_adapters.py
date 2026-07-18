"""Contract tests for the real hardware and AI adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.integration.adapters import (
    AdapterError,
    run_ai_pipeline,
    serialise_result,
)


@dataclass
class ExampleHardwareResult:
    passed: bool
    status: str
    results: dict
    failed_stage: str | None = None


def test_hardware_result_object_is_serialised() -> None:
    result = serialise_result(
        ExampleHardwareResult(
            passed=True,
            status="HARDWARE_VALIDATED",
            results={"yosys": {"passed": True}},
        )
    )

    assert result["passed"] is True
    assert result["status"] == "HARDWARE_VALIDATED"


class FakeAI:
    def analyze(self, evidence, controls):
        return {
            "feature_vector": {"values": [0.1]},
            "tensorflow": {"label": "CLEAN"},
            "pytorch": {"score": 0.02},
            "decision": {
                "classification": "CLEAN",
                "risk_score": 0.08,
                "confidence_score": 0.96,
            },
        }


def test_ai_adapter_calls_analyze() -> None:
    result = run_ai_pipeline(
        service=FakeAI(),
        simulation={
            "chip_id": "CHIP-TEST",
            "scenario": "GOOD_CHIP",
        },
        hardware_result={
            "service_output": {
                "results": {
                    "yosys": {"passed": True}
                }
            }
        },
    )

    assert result["passed"] is True
    assert result["classification"] == "CLEAN"
    assert result["risk_score"] == pytest.approx(0.08)


def test_missing_hardware_manifest_is_rejected() -> None:
    from app.integration.adapters import build_hardware_manifest

    with pytest.raises(AdapterError):
        build_hardware_manifest(
            project_root=Path(".").resolve(),
            simulation={"chip_id": "CHIP-TEST"},
        )
