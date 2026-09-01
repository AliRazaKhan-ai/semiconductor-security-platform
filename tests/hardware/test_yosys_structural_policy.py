"""Integration evidence for golden-reference Yosys structural policy."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.hardware.yosys import YosysAdapter
from app.hardware.yosys.rules import (
    evaluate_structural_delta,
    structural_delta_summary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REFERENCE_RTL = (
    PROJECT_ROOT
    / "hardware_lab/rtl/reference/semisecure_demo_core.sv"
)

CONTROLLED_TROJAN_RTL = (
    PROJECT_ROOT
    / "hardware_lab/rtl/controlled_trojan"
    / "semisecure_demo_core_trojan.sv"
)

TOP_MODULE = "semisecure_demo_core"


def _require_yosys() -> None:
    if shutil.which("yosys") is None:
        pytest.skip(
            "Required EDA tool is unavailable: yosys"
        )


@pytest.mark.integration
def test_structural_policy_flags_controlled_trojan_against_reference() -> None:
    _require_yosys()

    adapter = YosysAdapter.from_project(
        PROJECT_ROOT
    )

    reference = adapter.analyse(
        REFERENCE_RTL,
        TOP_MODULE,
    )

    candidate = adapter.analyse(
        CONTROLLED_TROJAN_RTL,
        TOP_MODULE,
    )

    assert evaluate_structural_delta(
        reference.metrics,
        reference.metrics,
        adapter.policy,
    ) == ()

    delta = structural_delta_summary(
        reference.metrics,
        candidate.metrics,
        adapter.policy,
    )

    reasons = set(
        evaluate_structural_delta(
            reference.metrics,
            candidate.metrics,
            adapter.policy,
        )
    )

    config = adapter.policy[
        "structural_baseline"
    ]

    assert (
        delta["absolute_cell_delta"]
        > config["maximum_absolute_cell_delta"]
    )

    assert (
        delta["absolute_wire_bit_delta"]
        > config["maximum_absolute_wire_bit_delta"]
    )

    assert (
        delta["absolute_public_wire_delta"]
        > config["maximum_absolute_public_wire_delta"]
    )

    assert (
        delta["additional_sequential_cells"]
        > config["maximum_additional_sequential_cells"]
    )

    assert (
        delta["additional_control_cells"]
        > config["maximum_additional_control_cells"]
    )

    assert (
        reference.netlist_digest
        != candidate.netlist_digest
    )

    assert {
        "STRUCTURAL_CELL_DELTA_EXCEEDED",
        "STRUCTURAL_WIRE_BIT_DELTA_EXCEEDED",
        "STRUCTURAL_PUBLIC_WIRE_DELTA_EXCEEDED",
        "STRUCTURAL_SEQUENTIAL_LOGIC_ADDED",
        "STRUCTURAL_CONTROL_LOGIC_ADDED",
    }.issubset(reasons)
