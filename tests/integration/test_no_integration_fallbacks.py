"""Prevent production integration from silently using scenario fallbacks."""

from __future__ import annotations

from pathlib import Path


def test_integration_has_no_scenario_ai_profiles() -> None:
    source = Path(
        "app/integration/service.py"
    ).read_text(encoding="utf-8")

    assert '"GOOD_CHIP": (' not in source
    assert '"HARDWARE_TROJAN": (' not in source
    assert '"WEAK_PUF": (' not in source
    assert '"SUPPLY_CHAIN_TAMPERING": (' not in source
    assert '"HIGH_RISK_SUPPLIER": (' not in source


def test_hardware_uses_explicit_strict_adapter() -> None:
    source = Path(
        "app/integration/service.py"
    ).read_text(encoding="utf-8")

    hardware_section = source[
        source.index("def _run_hardware"):
        source.index("def _run_ai")
    ]

    assert "run_hardware_pipeline(" in hardware_section
    assert "semisecure.hardware_pipeline" in hardware_section
    assert "_invoke_service(" not in hardware_section
    assert "optional=True" not in hardware_section


def test_ai_uses_explicit_strict_adapter() -> None:
    source = Path(
        "app/integration/service.py"
    ).read_text(encoding="utf-8")

    ai_section = source[
        source.index("def _run_ai"):
        source.index("def _run_compliance")
    ]

    assert "run_ai_pipeline(" in ai_section
    assert "semisecure.ai_pipeline" in ai_section
    assert "_invoke_service(" not in ai_section
    assert "optional=True" not in ai_section
