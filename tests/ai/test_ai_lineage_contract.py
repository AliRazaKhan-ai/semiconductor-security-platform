"""Tests for fail-closed AI training-run lineage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from app.ai.feature_extraction.schemas import FEATURE_NAMES

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_AI = ROOT / "scripts/ai"

sys.path.insert(
    0,
    str(SCRIPTS_AI),
)

from dataset import (  # noqa: E402
    build_split,
    save_split,
)
from lineage import (  # noqa: E402
    build_lineage_manifest,
    load_lineage_manifest,
    write_lineage_manifest,
)


def _prepare_artifacts(
    tmp_path: Path,
) -> dict[str, Path]:
    labels = np.repeat(
        np.arange(
            3,
            dtype=np.int64,
        ),
        40,
    )

    features = np.zeros(
        (
            len(labels),
            len(FEATURE_NAMES),
        ),
        dtype=np.float32,
    )

    sequences = np.zeros(
        (
            len(labels),
            256,
            3,
        ),
        dtype=np.float32,
    )

    dataset = (
        tmp_path
        / "dataset.npz"
    )

    np.savez_compressed(
        dataset,
        features=features,
        sequences=sequences,
        labels=labels,
    )

    split_path = (
        tmp_path
        / "split.json"
    )

    split = build_split(
        dataset,
        labels,
        seed=42,
    )

    save_split(
        split_path,
        split,
    )

    normalizer = (
        tmp_path
        / "normalizer.json"
    )

    normalizer.write_text(
        json.dumps(
            {
                "feature_names": (
                    FEATURE_NAMES
                ),
                "median": [
                    0.0
                    for _ in FEATURE_NAMES
                ],
                "scale": [
                    1.0
                    for _ in FEATURE_NAMES
                ],
            }
        ),
        encoding="utf-8",
    )

    signals = (
        tmp_path
        / "signals.npz"
    )

    values = np.zeros(
        len(labels),
        dtype=np.float32,
    )

    np.savez_compressed(
        signals,
        cnn_score=values,
        cnn_confidence=values,
        anomaly_score=values,
        anomaly_confidence=values,
        sample_indices=np.arange(
            len(labels),
            dtype=np.int64,
        ),
        dataset_sha256=np.asarray(
            split.dataset_sha256
        ),
        split_digest=np.asarray(
            split.split_digest
        ),
    )

    tensorflow_model = (
        tmp_path
        / "cnn.keras"
    )
    pytorch_model = (
        tmp_path
        / "ae.pt"
    )
    risk_model = (
        tmp_path
        / "risk.joblib"
    )

    tensorflow_model.write_bytes(
        b"tensorflow-model"
    )
    pytorch_model.write_bytes(
        b"pytorch-model"
    )
    risk_model.write_bytes(
        b"risk-model"
    )

    tensorflow_metrics = (
        tmp_path
        / "cnn.metrics.json"
    )
    pytorch_metrics = (
        tmp_path
        / "ae.metrics.json"
    )
    risk_metrics = (
        tmp_path
        / "risk.metrics.json"
    )

    tensorflow_metrics.write_text(
        json.dumps(
            {
                "evaluation_split": (
                    "TEST"
                ),
                "dataset_sha256": (
                    split.dataset_sha256
                ),
                "split_digest": (
                    split.split_digest
                ),
            }
        ),
        encoding="utf-8",
    )

    pytorch_metrics.write_text(
        json.dumps(
            {
                "threshold_source": (
                    "CLEAN_VALIDATION"
                ),
                "dataset_sha256": (
                    split.dataset_sha256
                ),
                "split_digest": (
                    split.split_digest
                ),
            }
        ),
        encoding="utf-8",
    )

    risk_metrics.write_text(
        json.dumps(
            {
                "evaluation_split": (
                    "TEST"
                ),
                "dataset_sha256": (
                    split.dataset_sha256
                ),
                "split_digest": (
                    split.split_digest
                ),
            }
        ),
        encoding="utf-8",
    )

    return {
        "dataset": dataset,
        "split": split_path,
        "normalizer": normalizer,
        "signals": signals,
        "tensorflow_model": (
            tensorflow_model
        ),
        "tensorflow_metrics": (
            tensorflow_metrics
        ),
        "pytorch_model": (
            pytorch_model
        ),
        "pytorch_metrics": (
            pytorch_metrics
        ),
        "risk_model": risk_model,
        "risk_metrics": risk_metrics,
    }


def _build(
    paths: dict[str, Path],
) -> dict:
    return build_lineage_manifest(
        project_root=ROOT,
        dataset_path=paths[
            "dataset"
        ],
        split_path=paths[
            "split"
        ],
        normalizer_path=paths[
            "normalizer"
        ],
        model_signals_path=paths[
            "signals"
        ],
        tensorflow_model_path=paths[
            "tensorflow_model"
        ],
        tensorflow_metrics_path=paths[
            "tensorflow_metrics"
        ],
        pytorch_model_path=paths[
            "pytorch_model"
        ],
        pytorch_metrics_path=paths[
            "pytorch_metrics"
        ],
        risk_model_path=paths[
            "risk_model"
        ],
        risk_metrics_path=paths[
            "risk_metrics"
        ],
        training_seed=42,
        created_at_utc=(
            "2026-08-19T00:00:00+00:00"
        ),
    )


def test_lineage_binds_training_artifacts(
    tmp_path: Path,
) -> None:
    paths = _prepare_artifacts(
        tmp_path
    )

    payload = _build(
        paths
    )

    assert (
        payload["status"]
        == "VERIFIED_TRAINING_RUN"
    )

    assert (
        payload[
            "dataset"
        ]["sha256"]
        == payload[
            "model_signals"
        ]["dataset_sha256"]
    )

    assert (
        payload[
            "split"
        ]["split_digest"]
        == payload[
            "model_signals"
        ]["split_digest"]
    )

    assert len(
        payload[
            "normalizer"
        ]["sha256"]
    ) == 64

    assert len(
        payload[
            "models"
        ]["tensorflow"][
            "artifact_sha256"
        ]
    ) == 64

    assert len(
        payload[
            "lineage_digest"
        ]
    ) == 64


def test_lineage_rejects_unbound_metrics(
    tmp_path: Path,
) -> None:
    paths = _prepare_artifacts(
        tmp_path
    )

    metrics = json.loads(
        paths[
            "tensorflow_metrics"
        ].read_text(
            encoding="utf-8"
        )
    )

    metrics[
        "dataset_sha256"
    ] = "0" * 64

    paths[
        "tensorflow_metrics"
    ].write_text(
        json.dumps(
            metrics
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            "tensorflow metrics "
            "dataset hash mismatch"
        ),
    ):
        _build(
            paths
        )


def test_lineage_digest_detects_mutation(
    tmp_path: Path,
) -> None:
    paths = _prepare_artifacts(
        tmp_path
    )

    payload = _build(
        paths
    )

    manifest = (
        tmp_path
        / "lineage.json"
    )

    write_lineage_manifest(
        manifest,
        payload,
    )

    loaded = json.loads(
        manifest.read_text(
            encoding="utf-8"
        )
    )

    loaded[
        "training"
    ]["seed"] = 99

    manifest.write_text(
        json.dumps(
            loaded
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            "lineage manifest digest "
            "verification failed"
        ),
    ):
        load_lineage_manifest(
            manifest
        )


def test_train_all_generates_lineage_last() -> None:
    source = (
        ROOT
        / "scripts/ai/train_all.sh"
    ).read_text(
        encoding="utf-8"
    )

    risk_position = source.index(
        "train_risk_engine.py"
    )

    lineage_position = source.index(
        "write_lineage_manifest.py"
    )

    assert (
        lineage_position
        > risk_position
    )

    assert (
        'SEED="${4:-42}"'
        in source
    )

    assert (
        '--output "$LINEAGE"'
        in source
    )
