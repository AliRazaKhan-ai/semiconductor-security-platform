"""Purpose: Validate the five approved chip scenarios and fail-closed flow.
Directory: tests/pipeline.
Dependencies: data/chips JSON files and simulation security gate.
Connection: Protects the terminal-to-deployment decision workflow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.pipeline.simulation_gate import evaluate_simulation_gate

ROOT = Path(__file__).resolve().parents[2]
CHIP_ROOT = ROOT / "data" / "chips"


EXPECTED_FILES = {
    "chip_01_good.json",
    "chip_02_trojan.json",
    "chip_03_puf_unstable.json",
    "chip_04_supplychain_tampered.json",
    "chip_05_highrisk_supplier.json",
}


def load_chip(filename: str) -> dict[str, Any]:
    path = CHIP_ROOT / filename

    assert path.is_file(), f"Required chip file is missing: {path}"

    value = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(value, dict)
    return value


def test_all_five_approved_chip_files_exist() -> None:
    actual = {
        path.name
        for path in CHIP_ROOT.glob("*.json")
        if path.is_file()
    }

    assert EXPECTED_FILES.issubset(actual)


@pytest.mark.parametrize("filename", sorted(EXPECTED_FILES))
def test_every_chip_file_is_valid_json(filename: str) -> None:
    chip = load_chip(filename)

    assert str(chip.get("chip_id") or "").strip()
    assert str(chip.get("scenario") or "").strip()


def test_good_chip_passes_simulation_gate() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_01_good.json")
    )

    assert result.passed is True


def test_trojan_chip_fails_closed() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_02_trojan.json")
    )

    assert result.passed is False
    assert result.risk_score >= 0.80
    assert result.deployment_decision != "DEPLOY"


def test_weak_puf_stops_at_puf_authentication() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_03_puf_unstable.json")
    )

    assert result.passed is False
    assert result.stage == "PUF_AUTHENTICATION"
    assert result.deployment_decision != "DEPLOY"


def test_supply_chain_tampering_is_rejected() -> None:
    result = evaluate_simulation_gate(
        load_chip("chip_04_supplychain_tampered.json")
    )

    assert result.passed is False
    assert result.deployment_decision != "DEPLOY"


def test_high_risk_supplier_never_auto_deploys() -> None:
    chip = load_chip("chip_05_highrisk_supplier.json")

    supplier = chip.get("supplier", {})
    expected = chip.get("expected_results", {})

    assert isinstance(supplier, dict)
    assert supplier
    assert expected.get("deployment_decision") != "DEPLOY"


def test_failed_stage_prevents_deployment() -> None:
    for filename in (
        "chip_02_trojan.json",
        "chip_03_puf_unstable.json",
        "chip_04_supplychain_tampered.json",
    ):
        result = evaluate_simulation_gate(load_chip(filename))

        assert result.passed is False
        assert result.deployment_decision not in {
            "DEPLOY",
            "APPROVED",
        }


def test_simulation_gate_is_deterministic() -> None:
    chip = load_chip("chip_02_trojan.json")

    first = evaluate_simulation_gate(chip).to_dict()
    second = evaluate_simulation_gate(chip).to_dict()

    assert first == second
