"""Tests for AI training/serving preprocessing and score parity."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.ai.tensorflow_classifier.postprocessing import postprocess

ROOT = Path(__file__).resolve().parents[2]


def test_cnn_score_is_non_clean_probability() -> None:
    labels = (
        "CLEAN",
        "TROJAN",
        "TAMPERED",
    )

    clean = postprocess(
        np.asarray(
            [
                0.90,
                0.07,
                0.03,
            ]
        ),
        labels,
    )

    trojan = postprocess(
        np.asarray(
            [
                0.10,
                0.80,
                0.10,
            ]
        ),
        labels,
    )

    assert np.isclose(
        clean["score"],
        0.10,
    )

    assert np.isclose(
        trojan["score"],
        0.90,
    )


def test_training_consumes_persisted_normalizer() -> None:
    names = (
        "train_pytorch_autoencoder.py",
        "generate_model_signals.py",
        "train_risk_engine.py",
    )

    for name in names:
        source = (
            ROOT
            / "scripts/ai"
            / name
        ).read_text(
            encoding="utf-8"
        )

        assert "--normalizer" in source
        assert "RobustNormalizer.load" in source
        assert "normalizer.transform" in source


def test_risk_training_uses_normalized_features() -> None:
    source = (
        ROOT
        / "scripts/ai/train_risk_engine.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "normalized_features"
        in source
    )

    assert (
        """normalized_features,
            signals,"""
        in source
    )


def test_signal_generator_normalizes_ae_features() -> None:
    source = (
        ROOT
        / "scripts/ai/generate_model_signals.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "features=normalized_features"
        in source
    )


def test_legacy_ae_calibration_override_is_retained_until_retraining() -> None:
    config = json.loads(
        (
            ROOT
            / "configs/application/ai.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    pytorch = config["ai"]["pytorch"]

    assert "threshold" in pytorch
    assert "scale" in pytorch
    assert float(
        pytorch["threshold"]
    ) >= 0.0
    assert float(
        pytorch["scale"]
    ) > 0.0


def test_runtime_supports_artifact_calibration_after_retraining() -> None:
    source = (
        ROOT
        / "app/ai/pytorch_anomaly/service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "LEGACY_CONFIG_OVERRIDE"
        in source
    )
    assert (
        "MODEL_ARTIFACT"
        in source
    )
    assert (
        "loaded.threshold"
        in source
    )
    assert (
        "loaded.scale"
        in source
    )
