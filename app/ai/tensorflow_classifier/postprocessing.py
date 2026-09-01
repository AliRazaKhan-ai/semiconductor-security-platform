"""Convert CNN probabilities into risk score, label, confidence, and uncertainty."""

from __future__ import annotations

import math

import numpy as np

from app.ai.common import clamp


def postprocess(
    probabilities: np.ndarray,
    labels: tuple[str, ...],
    min_confidence: float = 0.60,
) -> dict:
    if len(labels) != len(probabilities):
        raise ValueError("label count mismatch")

    if "CLEAN" not in labels:
        raise ValueError("CNN labels must include CLEAN")

    idx = int(
        np.argmax(probabilities)
    )

    top = float(
        probabilities[idx]
    )

    clean_index = labels.index(
        "CLEAN"
    )

    risk_score = clamp(
        1.0
        - float(
            probabilities[
                clean_index
            ]
        )
    )

    ordered = np.sort(
        probabilities
    )

    margin = float(
        ordered[-1]
        - ordered[-2]
    )

    entropy = float(
        -sum(
            probability
            * math.log(
                max(
                    probability,
                    1e-12,
                )
            )
            for probability
            in probabilities
        )
        / math.log(
            len(probabilities)
        )
    )

    confidence = clamp(
        0.55 * top
        + 0.30 * margin
        + 0.15 * (
            1.0
            - entropy
        )
    )

    label = (
        labels[idx]
        if confidence
        >= min_confidence
        else "INDETERMINATE"
    )

    return {
        "label": label,
        "score": risk_score,
        "confidence": confidence,
        "probabilities": {
            name: float(value)
            for name, value
            in zip(
                labels,
                probabilities,
                strict=True,
            )
        },
        "entropy": entropy,
        "margin": margin,
    }
