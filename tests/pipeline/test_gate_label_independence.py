"""Purpose: Prove the simulation gate decides on evidence, never on the scenario label.
Directory: tests/pipeline.
Dependencies: pytest, app.pipeline.simulation_gate.
Connection: Guards the Phase 2 removal of the scenario == "HARDWARE_TROJAN"
short-circuit. A label supplied in the input must never determine a verdict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app.pipeline.simulation_gate import evaluate_simulation_gate

ROOT = Path(__file__).resolve().parents[2]
GATE_SOURCE = ROOT / "app" / "pipeline" / "simulation_gate.py"


def clean_simulation(scenario: str) -> dict[str, Any]:
    """Return evidence that passes every gate, carrying the supplied label."""
    return {
        "chip_id": "TEST-LABEL-INDEPENDENCE",
        "scenario": scenario,
        "hardware_security": {
            "puf": {
                "authentication_expected": True,
                "stability_score": 0.98,
                "intra_device_hamming_distance": 0.02,
            },
            "opentitan": {
                "secure_boot": True,
                "otp_integrity": True,
                "rom_digest_valid": True,
                "debug_locked": True,
            },
            "verilator": {
                "simulation_passed": True,
                "simulation_failure_ratio": 0.0,
            },
            "yosys": {
                "rare_net_ratio": 0.0,
                "netlist_delta_ratio": 0.0,
            },
        },
        "supply_chain": {
            "digital_twin_match": True,
            "sbom_match": True,
            "custody_gap_ratio": 0.0,
            "sbom_mismatch_ratio": 0.0,
        },
    }


@pytest.mark.security
def test_trojan_evidence_fails_despite_a_benign_label() -> None:
    """Trojan evidence under a GOOD_CHIP label must still fail closed."""
    simulation = clean_simulation("GOOD_CHIP")
    simulation["hardware_security"]["yosys"]["netlist_delta_ratio"] = 0.50

    result = evaluate_simulation_gate(simulation)

    assert result.passed is False
    assert result.stage == "HARDWARE_TROJAN_ANALYSIS"
    assert result.classification == "HARDWARE_TROJAN"
    assert result.stop_pipeline is True


@pytest.mark.security
def test_clean_evidence_passes_despite_a_trojan_label() -> None:
    """A HARDWARE_TROJAN label must not by itself fail clean evidence."""
    result = evaluate_simulation_gate(clean_simulation("HARDWARE_TROJAN"))

    assert result.passed is True
    assert result.stage == "PRE_COMPLIANCE_SECURITY_GATES"
    assert result.stop_pipeline is False


@pytest.mark.security
def test_simulation_failure_evidence_still_fails() -> None:
    """Verilator evidence alone must be able to fail the gate."""
    simulation = clean_simulation("GOOD_CHIP")
    simulation["hardware_security"]["verilator"]["simulation_passed"] = False

    result = evaluate_simulation_gate(simulation)

    assert result.passed is False
    assert result.stage == "HARDWARE_TROJAN_ANALYSIS"


@pytest.mark.security
def test_gate_source_contains_no_scenario_comparison() -> None:
    """The gate must not compare the scenario label to any literal."""
    source = GATE_SOURCE.read_text(encoding="utf-8")
    offenders = re.findall(r"scenario\s*(?:==|!=|in)\s*[\[({\"']", source)

    assert not offenders, (
        "simulation_gate.py compares the scenario label to a literal: "
        f"{offenders}"
    )
