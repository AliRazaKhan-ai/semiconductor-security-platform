"""Tests for mandatory pre-AI risk-fusion controls."""

from app.ai.risk_engine.policy_fusion import fuse


def _controls(
    **overrides,
):
    values = {
        "puf_authenticated": True,
        "opentitan_verified": True,
        "digital_twin_verified": True,
        "hardware_ai_contract_complete": True,
    }

    values.update(
        overrides
    )

    return values


def test_failed_pre_ai_control_forces_high_risk() -> None:
    score, reasons = fuse(
        0.05,
        0.02,
        0.03,
        _controls(
            puf_authenticated=False
        ),
    )

    assert score >= 0.95
    assert reasons


def test_incomplete_hw_ai_contract_forces_high_risk() -> None:
    score, reasons = fuse(
        0.05,
        0.02,
        0.03,
        _controls(
            hardware_ai_contract_complete=False
        ),
    )

    assert score >= 0.95

    assert any(
        "hardware_ai_contract_complete"
        in reason
        for reason in reasons
    )


def test_compliance_is_not_a_pre_ai_control() -> None:
    score, reasons = fuse(
        0.05,
        0.02,
        0.03,
        _controls(),
    )

    assert score < 0.95

    assert all(
        "compliance"
        not in reason
        for reason in reasons
    )
