"""Fail-closed fusion of learned risk and mandatory pre-AI security controls."""

from __future__ import annotations

from typing import Any

from app.ai.common import clamp


def fuse(
    base_risk: float,
    cnn_score: float,
    anomaly_score: float,
    controls: dict[str, Any],
) -> tuple[float, list[str]]:
    reasons: list[str] = []

    mandatory = {
        "puf_authenticated": controls.get(
            "puf_authenticated",
            False,
        ),
        "opentitan_verified": controls.get(
            "opentitan_verified",
            False,
        ),
        "digital_twin_verified": controls.get(
            "digital_twin_verified",
            False,
        ),
        "hardware_ai_contract_complete": controls.get(
            "hardware_ai_contract_complete",
            False,
        ),
    }

    failed = [
        name
        for name, passed
        in mandatory.items()
        if not passed
    ]

    score = clamp(
        0.45 * base_risk
        + 0.30 * cnn_score
        + 0.25 * anomaly_score
    )

    if failed:
        score = max(
            score,
            0.95,
        )

        reasons.extend(
            f"mandatory control failed: {name}"
            for name in failed
        )

    if controls.get(
        "sbom_mismatch",
        False,
    ):
        score = max(
            score,
            0.80,
        )

        reasons.append(
            "SBOM mismatch"
        )

    if controls.get(
        "custody_tampered",
        False,
    ):
        score = max(
            score,
            0.90,
        )

        reasons.append(
            "custody provenance tampering"
        )

    return score, reasons
