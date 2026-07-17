"""Purpose: Test fail-closed pre-compliance semiconductor security gates.
Directory: tests/unit.
Dependencies: app.pipeline.simulation_gate.
Connection: Protects five-scenario Phase 3 pipeline behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.pipeline.simulation_gate import evaluate_simulation_gate


def load_chip(filename: str) -> dict:
    path = Path("data/chips") / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_good_chip_passes_security_gates() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_01_good.json")
    )

    assert result.passed is True
    assert result.stop_pipeline is False


def test_trojan_chip_stops_pipeline() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_02_trojan.json")
    )

    assert result.passed is False
    assert result.stage == "HARDWARE_TROJAN_ANALYSIS"
    assert result.deployment_decision == "DENIED_AND_QUARANTINED"


def test_weak_puf_stops_at_authentication() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_03_puf_unstable.json")
    )

    assert result.passed is False
    assert result.stage == "PUF_AUTHENTICATION"
    assert result.stop_pipeline is True
    assert result.classification == "PUF_AUTHENTICATION_FAILED"


def test_supply_chain_tampering_stops_pipeline() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_04_supplychain_tampered.json")
    )

    assert result.passed is False
    assert result.stage in {
        "OPENTITAN",
        "DIGITAL_TWIN_AND_SBOM",
    }


def test_high_risk_supplier_passes_hardware_then_reaches_compliance() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_05_highrisk_supplier.json")
    )

    assert result.passed is True
    assert result.stop_pipeline is False
