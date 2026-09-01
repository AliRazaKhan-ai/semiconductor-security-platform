"""Tests for the canonical AI dataset split contract."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_AI = ROOT / "scripts" / "ai"

sys.path.insert(
    0,
    str(SCRIPTS_AI),
)

from dataset import (  # noqa: E402
    build_split,
    load_dataset,
    load_model_signals,
    load_split,
    save_split,
)


def _write_dataset(
    path: Path,
    *,
    samples_per_class: int = 40,
) -> np.ndarray:
    labels = np.repeat(
        np.arange(
            3,
            dtype=np.int64,
        ),
        samples_per_class,
    )

    features = np.zeros(
        (
            len(labels),
            32,
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

    np.savez_compressed(
        path,
        features=features,
        sequences=sequences,
        labels=labels,
    )

    return labels


def test_split_is_deterministic_disjoint_and_complete(
    tmp_path: Path,
) -> None:
    dataset = (
        tmp_path
        / "dataset.npz"
    )

    labels = _write_dataset(
        dataset
    )

    first = build_split(
        dataset,
        labels,
        seed=42,
    )

    second = build_split(
        dataset,
        labels,
        seed=42,
    )

    assert first == second

    train = set(
        first.train_indices
    )
    validation = set(
        first.validation_indices
    )
    test = set(
        first.test_indices
    )

    assert not (
        train & validation
    )
    assert not (
        train & test
    )
    assert not (
        validation & test
    )

    assert (
        train
        | validation
        | test
    ) == set(
        range(
            len(labels)
        )
    )


def test_split_is_bound_to_dataset_hash(
    tmp_path: Path,
) -> None:
    dataset = (
        tmp_path
        / "dataset.npz"
    )

    split_path = (
        tmp_path
        / "split.json"
    )

    labels = _write_dataset(
        dataset
    )

    split = build_split(
        dataset,
        labels,
    )

    save_split(
        split_path,
        split,
    )

    load_split(
        split_path,
        dataset,
        labels,
    )

    dataset.write_bytes(
        dataset.read_bytes()
        + b"changed"
    )

    with pytest.raises(
        ValueError,
        match="different dataset",
    ):
        load_split(
            split_path,
            dataset,
            labels,
        )


def test_model_signals_are_bound_to_same_split(
    tmp_path: Path,
) -> None:
    dataset = (
        tmp_path
        / "dataset.npz"
    )

    labels = _write_dataset(
        dataset
    )

    split = build_split(
        dataset,
        labels,
    )

    signals_path = (
        tmp_path
        / "signals.npz"
    )

    values = np.zeros(
        len(labels),
        dtype=np.float32,
    )

    np.savez_compressed(
        signals_path,
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

    loaded = load_model_signals(
        signals_path,
        split,
    )

    assert loaded.shape == (
        len(labels),
        4,
    )


def test_training_scripts_use_shared_split_contract() -> None:
    names = (
        "train_normalizer.py",
        "train_tensorflow_cnn.py",
        "train_pytorch_autoencoder.py",
        "generate_model_signals.py",
        "train_risk_engine.py",
    )

    for name in names:
        source = (
            SCRIPTS_AI
            / name
        ).read_text(
            encoding="utf-8"
        )

        assert "--split" in source
        assert "load_split" in source

    cnn_source = (
        SCRIPTS_AI
        / "train_tensorflow_cnn.py"
    ).read_text(
        encoding="utf-8"
    )

    risk_source = (
        SCRIPTS_AI
        / "train_risk_engine.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "np.random.shuffle"
        not in cnn_source
    )

    assert (
        "train_test_split"
        not in risk_source
    )


def test_project_split_matches_current_dataset() -> None:
    dataset_path = (
        ROOT
        / "data/training/semiconductor_ai.npz"
    )

    split_path = (
        ROOT
        / "data/training/semiconductor_ai.split.json"
    )

    _, _, labels = load_dataset(
        dataset_path
    )

    split = load_split(
        split_path,
        dataset_path,
        labels,
    )

    assert split.sample_count == 5000
    assert len(
        split.train_indices
    ) == 3500
    assert len(
        split.validation_indices
    ) == 750
    assert len(
        split.test_indices
    ) == 750

    assert split.dataset_sha256 == (
        "dedd49ae00260443528668bd70544349e"
        "37bf105dd4523cd901501679ab93239"
    )
