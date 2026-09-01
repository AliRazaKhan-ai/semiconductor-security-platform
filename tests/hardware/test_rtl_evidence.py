"""Integration evidence for the controlled RTL reference and Trojan variant."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.hardware.common import HardwareIntegrationError
from app.hardware.verilator import VerilatorAdapter
from app.hardware.yosys import YosysAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_ROOT = PROJECT_ROOT / "hardware_lab" / "rtl" / "manifests"


def _manifest(name: str) -> dict[str, object]:
    path = MANIFEST_ROOT / name
    return json.loads(path.read_text(encoding="utf-8"))


def _path(value: object) -> Path:
    return PROJECT_ROOT / str(value)


def _require_eda_tools() -> None:
    missing = [
        name
        for name in ("yosys", "verilator")
        if shutil.which(name) is None
    ]

    if missing:
        pytest.skip(
            "Required EDA tools are unavailable: "
            + ", ".join(missing)
        )


@pytest.mark.integration
def test_yosys_synthesises_reference_and_controlled_trojan() -> None:
    _require_eda_tools()

    clean = _manifest("clean_rtl_evidence.json")
    trojan = _manifest(
        "controlled_trojan_rtl_evidence.json"
    )

    adapter = YosysAdapter.from_project(PROJECT_ROOT)

    clean_result = adapter.analyse(
        _path(clean["rtl_file"]),
        str(clean["rtl_top_module"]),
    )

    trojan_result = adapter.analyse(
        _path(trojan["rtl_file"]),
        str(trojan["rtl_top_module"]),
    )

    assert clean_result.passed is True
    assert trojan_result.passed is True
    assert (
        clean_result.netlist_digest
        != trojan_result.netlist_digest
    )
    assert (
        clean_result.rtl_digest
        != trojan_result.rtl_digest
    )


@pytest.mark.integration
def test_verilator_reference_passes_and_trojan_payload_is_detected() -> None:
    _require_eda_tools()

    clean = _manifest("clean_rtl_evidence.json")
    trojan = _manifest(
        "controlled_trojan_rtl_evidence.json"
    )

    adapter = VerilatorAdapter()

    clean_result = adapter.simulate(
        _path(clean["rtl_file"]),
        _path(clean["testbench_file"]),
        str(clean["verilator_top_module"]),
    )

    assert clean_result.passed is True
    assert clean_result.cycles == 12
    assert clean_result.assertions >= 12

    with pytest.raises(
        HardwareIntegrationError,
        match="RTL simulation failed",
    ):
        adapter.simulate(
            _path(trojan["rtl_file"]),
            _path(trojan["testbench_file"]),
            str(trojan["verilator_top_module"]),
        )
