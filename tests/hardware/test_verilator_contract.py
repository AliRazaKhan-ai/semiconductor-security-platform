"""Tests for the Verilator verification-evidence contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.hardware.verilator.result_parser import parse_output
from app.hardware.verilator.testbench import validate_testbench


def test_marker_only_testbench_is_rejected(tmp_path: Path) -> None:
    testbench = tmp_path / "tb_marker_only.sv"
    testbench.write_text(
        'module tb; initial begin $display("SEMISURE_PASS"); '
        "$finish; end endmodule\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="verification summary markers",
    ):
        validate_testbench(testbench)


def test_marker_only_output_is_not_a_pass() -> None:
    reasons, assertions, cycles, warnings = parse_output(
        "",
        "SEMISURE_PASS\n",
    )

    assert assertions == 0
    assert cycles == 0
    assert warnings == ()

    assert {
        "ASSERTION_SUMMARY_MISSING",
        "CYCLE_SUMMARY_MISSING",
        "RESET_COMPLETION_MISSING",
        "REQUIRED_CHECKS_MISSING",
    }.issubset(set(reasons))


def test_complete_verification_summary_is_accepted() -> None:
    output = "\n".join(
        (
            "RESET_COMPLETED=1",
            "REQUIRED_CHECKS_PASSED=1",
            "ASSERTIONS=24",
            "CYCLES=12",
            "SEMISURE_PASS",
        )
    )

    reasons, assertions, cycles, warnings = parse_output(
        "",
        output,
    )

    assert reasons == ()
    assert assertions == 24
    assert cycles == 12
    assert warnings == ()
