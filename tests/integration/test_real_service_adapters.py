"""Contract tests for strict hardware and AI integration adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.hardware.common import sha256_file
from app.integration.adapters import (
    AdapterError,
    build_ai_controls,
    build_ai_evidence,
    build_hardware_manifest,
    run_ai_pipeline,
    serialise_result,
)


@dataclass
class ExampleHardwareResult:
    passed: bool
    status: str
    results: dict
    failed_stage: str | None = None


def _write_trace(
    path: Path,
    *,
    source_type: str = "OFFLINE_TRACE",
) -> None:
    path.write_text(
        json.dumps(
            {
                "samples": [
                    float(
                        (index % 17)
                        - 8
                    )
                    for index
                    in range(256)
                ],
                "provenance": {
                    "source_type": (
                        source_type
                    )
                },
            }
        ),
        encoding="utf-8",
    )


def _evidence_fixture(
    tmp_path: Path,
) -> tuple[
    dict,
    dict,
]:
    power = (
        tmp_path
        / "power.json"
    )
    reference = (
        tmp_path
        / "reference.json"
    )
    em = (
        tmp_path
        / "em.json"
    )
    timing = (
        tmp_path
        / "timing.json"
    )

    for path in (
        power,
        reference,
        em,
        timing,
    ):
        _write_trace(
            path
        )

    hardware = {
        "passed": True,
        "manifest": {
            "side_channel_trace": str(
                power
            ),
            "side_channel_reference": str(
                reference
            ),
            "ai_em_trace": str(
                em
            ),
            "ai_timing_trace": str(
                timing
            ),
        },
        "service_output": {
            "passed": True,
            "status": (
                "HARDWARE_VALIDATED"
            ),
            "results": {
                "opentitan": {
                    "passed": True,
                    "status": "ATTESTED",
                    "evidence_digest": (
                        "a" * 64
                    ),
                    "lifecycle_state": (
                        "PROD"
                    ),
                    "firmware_digest": (
                        "b" * 64
                    ),
                    "monotonic_counter": 7,
                },
                "chipwhisperer": {
                    "passed": True,
                    "status": "CLEAN",
                    "analysis_mode": (
                        "FILE_BASED_OFFLINE_ANALYSIS"
                    ),
                    "candidate_source_type": (
                        "OFFLINE_TRACE"
                    ),
                    "reference_source_type": (
                        "OFFLINE_TRACE"
                    ),
                    "candidate_file_digest": (
                        sha256_file(
                            power
                        )
                    ),
                    "reference_file_digest": (
                        sha256_file(
                            reference
                        )
                    ),
                    "physical_capture_verified": (
                        False
                    ),
                },
                "yosys": {
                    "passed": True,
                    "status": "PASS",
                    "metrics": {
                        "wires": 15,
                        "wire_bits": 55,
                        "public_wires": 9,
                        "cells": 8,
                        "processes": 0,
                        "memories": 0,
                        "memory_bits": 0,
                        "cell_types": {
                            "$add": 1,
                            "$adff": 1,
                            "$adffe": 1,
                            "$eq": 2,
                            "$logic_not": 1,
                            "$not": 1,
                            "$pmux": 1,
                        },
                    },
                },
                "verilator": {
                    "passed": True,
                    "status": "PASS",
                    "assertions": 24,
                    "cycles": 12,
                },
                "sbom": {
                    "passed": True,
                    "status": "GENERATED",
                },
                "digital_twin": {
                    "passed": True,
                    "status": "VERIFIED",
                },
            },
        },
    }

    puf = {
        "passed": True,
        "classification": (
            "PUF_AUTHENTICATED"
        ),
        "details": {
            "stability_score": 0.99,
        },
        "verification_source": (
            "SIMULATED_PUF_FIXTURE"
        ),
    }

    return hardware, puf


def test_hardware_result_object_is_serialised() -> None:
    result = serialise_result(
        ExampleHardwareResult(
            passed=True,
            status="HARDWARE_VALIDATED",
            results={
                "yosys": {
                    "passed": True
                }
            },
        )
    )

    assert result[
        "passed"
    ] is True

    assert (
        result["status"]
        == "HARDWARE_VALIDATED"
    )


def test_ai_evidence_uses_verified_hardware_outputs(
    tmp_path: Path,
) -> None:
    hardware, puf = (
        _evidence_fixture(
            tmp_path
        )
    )

    evidence = build_ai_evidence(
        simulation={
            "chip_id": "CHIP-TEST",
            "scenario": "GOOD_CHIP",
        },
        puf_result=puf,
        hardware_result=hardware,
    )

    assert len(
        evidence[
            "side_channel"
        ]["power_trace"]
    ) == 256

    assert len(
        evidence[
            "side_channel"
        ]["em_trace"]
    ) == 256

    assert len(
        evidence[
            "side_channel"
        ]["timing_trace"]
    ) == 256

    assert (
        evidence[
            "yosys"
        ]["cell_count"]
        == 8
    )

    assert (
        evidence[
            "verilator"
        ]["failed_assertions"]
        == 0
    )

    assert (
        evidence[
            "opentitan"
        ]["verified"]
        is True
    )

    assert (
        evidence[
            "evidence_provenance"
        ]["power_source_type"]
        == "OFFLINE_TRACE"
    )

    assert (
        evidence[
            "evidence_quality"
        ]
        == 0.0
    )

    assert (
        evidence[
            "hardware_ai_contract_complete"
        ]
        is False
    )


def test_ai_controls_derive_from_preceding_stages(
    tmp_path: Path,
) -> None:
    hardware, puf = (
        _evidence_fixture(
            tmp_path
        )
    )

    simulation = {
        "chip_id": "CHIP-TEST",
    }

    evidence = build_ai_evidence(
        simulation=simulation,
        puf_result=puf,
        hardware_result=hardware,
    )

    controls = build_ai_controls(
        simulation=simulation,
        puf_result=puf,
        hardware_result=hardware,
        evidence=evidence,
    )

    assert (
        controls[
            "puf_authenticated"
        ]
        is False
    )

    assert (
        controls[
            "puf_evidence_class"
        ]
        == "SIMULATED_PUF_FIXTURE"
    )

    assert (
        controls[
            "opentitan_verified"
        ]
        is True
    )

    assert (
        controls[
            "digital_twin_verified"
        ]
        is True
    )

    assert (
        controls[
            "hardware_ai_contract_complete"
        ]
        is False
    )

    assert (
        "compliance_passed"
        not in controls
    )


class FakeAI:
    def __init__(
        self,
    ) -> None:
        self.called = False

    def analyze(
        self,
        evidence,
        controls,
    ):
        self.called = True

        return {
            "feature_vector": {
                "values": [
                    0.1
                ]
            },
            "decision": {
                "classification": (
                    "CLEAN"
                ),
                "risk_score": 0.08,
                "confidence_score": (
                    0.96
                ),
            },
        }


def test_incomplete_hardware_ai_contract_fails_before_model(
    tmp_path: Path,
) -> None:
    hardware, puf = (
        _evidence_fixture(
            tmp_path
        )
    )

    ai = FakeAI()

    with pytest.raises(
        AdapterError,
        match=(
            "Hardware-to-AI feature "
            "contract is incomplete"
        ),
    ):
        run_ai_pipeline(
            service=ai,
            simulation={
                "chip_id": (
                    "CHIP-TEST"
                ),
                "scenario": (
                    "GOOD_CHIP"
                ),
            },
            puf_result=puf,
            hardware_result=hardware,
        )

    assert ai.called is False


def test_simulation_ai_override_is_rejected(
    tmp_path: Path,
) -> None:
    hardware, puf = (
        _evidence_fixture(
            tmp_path
        )
    )

    with pytest.raises(
        AdapterError,
        match="ai_evidence overrides",
    ):
        build_ai_evidence(
            simulation={
                "chip_id": (
                    "CHIP-TEST"
                ),
                "ai_evidence": {
                    "yosys": {
                        "gate_count": 1
                    }
                },
            },
            puf_result=puf,
            hardware_result=hardware,
        )


def test_missing_hardware_manifest_is_rejected() -> None:
    with pytest.raises(
        AdapterError
    ):
        build_hardware_manifest(
            project_root=Path(
                "."
            ).resolve(),
            simulation={
                "chip_id": (
                    "CHIP-TEST"
                )
            },
        )
