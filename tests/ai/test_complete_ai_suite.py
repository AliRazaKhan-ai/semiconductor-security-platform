"""Purpose: Validate AI service registration, contracts and fail-closed design.
Directory: tests/ai.
Dependencies: Flask factory and AI pipeline modules.
Connection: Protects TensorFlow, PyTorch, feature extraction and risk decision
integration without replacing model output with scenario-name fallbacks.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_ai_pipeline_service_is_registered() -> None:
    app = create_app({"TESTING": True})

    service = app.extensions.get("semisecure.ai_pipeline")

    assert service is not None
    assert type(service).__name__ == "AIPipelineService"


def test_ai_pipeline_exposes_exact_analyze_contract() -> None:
    app = create_app({"TESTING": True})
    service = app.extensions["semisecure.ai_pipeline"]

    analyze = getattr(service, "analyze", None)

    assert callable(analyze)

    parameters = inspect.signature(analyze).parameters

    assert "evidence" in parameters
    assert "controls" in parameters


def test_integration_uses_real_ai_adapter() -> None:
    source = (
        ROOT / "app" / "integration" / "service.py"
    ).read_text(encoding="utf-8")

    ai_section = source[
        source.index("def _run_ai"):
        source.index("def _run_compliance")
    ]

    assert "run_ai_pipeline(" in ai_section
    assert "semisecure.ai_pipeline" in ai_section


def test_ai_integration_contains_no_scenario_lookup_table() -> None:
    source = (
        ROOT / "app" / "integration" / "service.py"
    ).read_text(encoding="utf-8")

    forbidden_profiles = (
        '"GOOD_CHIP": (',
        '"HARDWARE_TROJAN": (',
        '"WEAK_PUF": (',
        '"SUPPLY_CHAIN_TAMPERING": (',
        '"HIGH_RISK_SUPPLIER": (',
    )

    for profile in forbidden_profiles:
        assert profile not in source


def test_ai_adapter_requires_real_decision_dictionary() -> None:
    source = (
        ROOT / "app" / "integration" / "adapters.py"
    ).read_text(encoding="utf-8")

    assert 'result.get("decision")' in source
    assert "AI pipeline result contains no decision dictionary" in source


def test_tensorflow_and_pytorch_are_declared_dependencies() -> None:
    requirements = (
        ROOT / "requirements.txt"
    ).read_text(encoding="utf-8").lower()

    assert "tensorflow" in requirements
    assert "torch" in requirements or "pytorch" in requirements


def test_ai_risk_values_are_bounded_in_adapter() -> None:
    source = (
        ROOT / "app" / "integration" / "adapters.py"
    ).read_text(encoding="utf-8")

    assert "max(0.0, min(1.0, risk_score))" in source
    assert "max(0.0, min(1.0, confidence))" in source
