"""Tests for side-channel evidence provenance classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.hardware.chipwhisperer.adapter import (
    ChipWhispererAdapter,
)
from app.hardware.common import (
    HardwareIntegrationError,
    sha256_file,
)


def _samples() -> list[float]:
    return [
        float((index % 17) - 8)
        for index in range(256)
    ]


def _write_trace(
    path: Path,
    *,
    source_type: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "samples": _samples(),
    }

    if source_type is not None:
        payload["provenance"] = {
            "source_type": source_type,
        }

    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )


def test_legacy_trace_is_explicitly_offline(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate
    )
    _write_trace(
        reference
    )

    result = (
        ChipWhispererAdapter()
        .analyse_files(
            candidate,
            reference,
        )
    )

    assert result.passed is True
    assert (
        result.analysis_mode
        == "FILE_BASED_OFFLINE_ANALYSIS"
    )
    assert (
        result.candidate_source_type
        == "OFFLINE_TRACE"
    )
    assert (
        result.reference_source_type
        == "OFFLINE_TRACE"
    )
    assert (
        result.physical_capture_verified
        is False
    )


def test_simulated_trace_is_labelled_simulated(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate,
        source_type="SIMULATED_TRACE",
    )

    _write_trace(
        reference,
        source_type="SIMULATED_TRACE",
    )

    result = (
        ChipWhispererAdapter()
        .analyse_files(
            candidate,
            reference,
        )
    )

    assert (
        result.candidate_source_type
        == "SIMULATED_TRACE"
    )
    assert (
        result.reference_source_type
        == "SIMULATED_TRACE"
    )
    assert (
        result.physical_capture_verified
        is False
    )


def test_imported_trace_is_labelled_imported(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate,
        source_type="IMPORTED_TRACE",
    )

    _write_trace(
        reference,
        source_type="IMPORTED_TRACE",
    )

    result = (
        ChipWhispererAdapter()
        .analyse_files(
            candidate,
            reference,
        )
    )

    assert (
        result.candidate_source_type
        == "IMPORTED_TRACE"
    )


def test_physical_capture_claim_fails_closed(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate,
        source_type="PHYSICAL_CAPTURE",
    )

    _write_trace(
        reference
    )

    with pytest.raises(
        HardwareIntegrationError,
        match="physical ChipWhisperer capture",
    ):
        ChipWhispererAdapter().analyse_files(
            candidate,
            reference,
        )


def test_unknown_source_type_is_rejected(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate,
        source_type="UNVERIFIED_SCOPE_CAPTURE",
    )

    _write_trace(
        reference
    )

    with pytest.raises(
        HardwareIntegrationError,
        match="unsupported source_type",
    ):
        ChipWhispererAdapter().analyse_files(
            candidate,
            reference,
        )


def test_result_binds_source_file_hashes(
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / "candidate.json"
    )

    reference = (
        tmp_path
        / "reference.json"
    )

    _write_trace(
        candidate
    )

    _write_trace(
        reference
    )

    result = (
        ChipWhispererAdapter()
        .analyse_files(
            candidate,
            reference,
        )
    )

    assert (
        result.candidate_file_digest
        == sha256_file(candidate)
    )

    assert (
        result.reference_file_digest
        == sha256_file(reference)
    )


def test_configuration_cannot_enable_physical_capture(
    tmp_path: Path,
) -> None:
    config_root = (
        tmp_path
        / "configs/hardware"
    )

    config_root.mkdir(
        parents=True
    )

    (
        config_root
        / "chipwhisperer.json"
    ).write_text(
        json.dumps(
            {
                "version": "1.1",
                "anomaly_threshold": 0.35,
                "allowed_source_types": [
                    "OFFLINE_TRACE",
                    "PHYSICAL_CAPTURE",
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        HardwareIntegrationError,
        match=(
            "Invalid ChipWhisperer "
            "provenance configuration"
        ),
    ):
        ChipWhispererAdapter.from_project(
            tmp_path
        )
