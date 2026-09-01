"""Validated datasets and deterministic shared AI split contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import train_test_split

_SPLIT_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    version: str
    dataset_sha256: str
    sample_count: int
    seed: int
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    split_digest: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_dataset(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        required = {
            "features",
            "sequences",
            "labels",
        }

        if not required.issubset(data.files):
            raise ValueError(
                f"dataset must contain {sorted(required)}"
            )

        features = np.asarray(
            data["features"],
            dtype=np.float32,
        )
        sequences = np.asarray(
            data["sequences"],
            dtype=np.float32,
        )
        labels = np.asarray(
            data["labels"],
            dtype=np.int64,
        )

    if (
        features.ndim != 2
        or sequences.ndim != 3
        or sequences.shape[-1] != 3
        or len(features) != len(sequences)
        or len(features) != len(labels)
    ):
        raise ValueError(
            "invalid dataset dimensions"
        )

    return features, sequences, labels


def _split_payload(
    split: DatasetSplit,
) -> dict[str, Any]:
    return {
        "version": split.version,
        "dataset_sha256": split.dataset_sha256,
        "sample_count": split.sample_count,
        "seed": split.seed,
        "train_fraction": split.train_fraction,
        "validation_fraction": split.validation_fraction,
        "test_fraction": split.test_fraction,
        "train_indices": list(
            split.train_indices
        ),
        "validation_indices": list(
            split.validation_indices
        ),
        "test_indices": list(
            split.test_indices
        ),
    }


def _digest_payload(
    payload: dict[str, Any],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _validate_fractions(
    train_fraction: float,
    validation_fraction: float,
    test_fraction: float,
) -> None:
    fractions = (
        train_fraction,
        validation_fraction,
        test_fraction,
    )

    if any(
        value <= 0.0 or value >= 1.0
        for value in fractions
    ):
        raise ValueError(
            "split fractions must each be between 0 and 1"
        )

    if not np.isclose(
        sum(fractions),
        1.0,
        atol=1e-12,
    ):
        raise ValueError(
            "split fractions must sum to 1.0"
        )


def _validate_indices(
    split: DatasetSplit,
    labels: np.ndarray,
) -> None:
    partitions = (
        split.train_indices,
        split.validation_indices,
        split.test_indices,
    )

    if split.sample_count != len(labels):
        raise ValueError(
            "split sample count does not match dataset"
        )

    if any(
        not values
        for values in partitions
    ):
        raise ValueError(
            "train, validation and test partitions must be non-empty"
        )

    combined = [
        index
        for values in partitions
        for index in values
    ]

    if len(combined) != split.sample_count:
        raise ValueError(
            "split does not contain every sample exactly once"
        )

    if len(set(combined)) != split.sample_count:
        raise ValueError(
            "split partitions overlap"
        )

    if sorted(combined) != list(
        range(split.sample_count)
    ):
        raise ValueError(
            "split indices do not match canonical sample indices"
        )


def build_split(
    dataset_path: Path,
    labels: np.ndarray,
    *,
    seed: int = 42,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    test_fraction: float = 0.15,
) -> DatasetSplit:
    _validate_fractions(
        train_fraction,
        validation_fraction,
        test_fraction,
    )

    indices = np.arange(
        len(labels),
        dtype=np.int64,
    )

    train_indices, remainder = train_test_split(
        indices,
        train_size=train_fraction,
        stratify=labels,
        random_state=seed,
    )

    validation_share = (
        validation_fraction
        / (
            validation_fraction
            + test_fraction
        )
    )

    validation_indices, test_indices = (
        train_test_split(
            remainder,
            train_size=validation_share,
            stratify=labels[remainder],
            random_state=seed,
        )
    )

    provisional = DatasetSplit(
        version=_SPLIT_VERSION,
        dataset_sha256=sha256_file(
            dataset_path
        ),
        sample_count=len(labels),
        seed=seed,
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        train_indices=tuple(
            sorted(
                int(value)
                for value
                in train_indices
            )
        ),
        validation_indices=tuple(
            sorted(
                int(value)
                for value
                in validation_indices
            )
        ),
        test_indices=tuple(
            sorted(
                int(value)
                for value
                in test_indices
            )
        ),
        split_digest="",
    )

    digest = _digest_payload(
        _split_payload(
            provisional
        )
    )

    split = DatasetSplit(
        version=provisional.version,
        dataset_sha256=provisional.dataset_sha256,
        sample_count=provisional.sample_count,
        seed=provisional.seed,
        train_fraction=provisional.train_fraction,
        validation_fraction=provisional.validation_fraction,
        test_fraction=provisional.test_fraction,
        train_indices=provisional.train_indices,
        validation_indices=provisional.validation_indices,
        test_indices=provisional.test_indices,
        split_digest=digest,
    )

    _validate_indices(
        split,
        labels,
    )

    return split


def save_split(
    path: Path,
    split: DatasetSplit,
) -> None:
    payload = _split_payload(
        split
    )
    payload["split_digest"] = (
        split.split_digest
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_split(
    path: Path,
    dataset_path: Path,
    labels: np.ndarray,
) -> DatasetSplit:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "split file must contain a JSON object"
        )

    stored_digest = str(
        payload.get(
            "split_digest",
            "",
        )
    )

    raw = dict(
        payload
    )
    raw.pop(
        "split_digest",
        None,
    )

    expected_digest = _digest_payload(
        raw
    )

    if (
        not stored_digest
        or stored_digest
        != expected_digest
    ):
        raise ValueError(
            "split digest verification failed"
        )

    split = DatasetSplit(
        version=str(
            raw["version"]
        ),
        dataset_sha256=str(
            raw["dataset_sha256"]
        ),
        sample_count=int(
            raw["sample_count"]
        ),
        seed=int(
            raw["seed"]
        ),
        train_fraction=float(
            raw["train_fraction"]
        ),
        validation_fraction=float(
            raw["validation_fraction"]
        ),
        test_fraction=float(
            raw["test_fraction"]
        ),
        train_indices=tuple(
            int(value)
            for value
            in raw["train_indices"]
        ),
        validation_indices=tuple(
            int(value)
            for value
            in raw["validation_indices"]
        ),
        test_indices=tuple(
            int(value)
            for value
            in raw["test_indices"]
        ),
        split_digest=stored_digest,
    )

    if split.version != _SPLIT_VERSION:
        raise ValueError(
            "unsupported dataset split version"
        )

    _validate_fractions(
        split.train_fraction,
        split.validation_fraction,
        split.test_fraction,
    )

    _validate_indices(
        split,
        labels,
    )

    actual_dataset_hash = sha256_file(
        dataset_path
    )

    if (
        split.dataset_sha256
        != actual_dataset_hash
    ):
        raise ValueError(
            "split is bound to a different dataset"
        )

    return split


def load_model_signals(
    path: Path,
    split: DatasetSplit,
) -> np.ndarray:
    with np.load(
        path,
        allow_pickle=False,
    ) as data:
        required = {
            "cnn_score",
            "cnn_confidence",
            "anomaly_score",
            "anomaly_confidence",
            "sample_indices",
            "dataset_sha256",
            "split_digest",
        }

        if not required.issubset(
            data.files
        ):
            raise ValueError(
                "model signals lack canonical split metadata"
            )

        dataset_sha256 = str(
            np.asarray(
                data["dataset_sha256"]
            ).item()
        )

        split_digest = str(
            np.asarray(
                data["split_digest"]
            ).item()
        )

        sample_indices = np.asarray(
            data["sample_indices"],
            dtype=np.int64,
        )

        if (
            dataset_sha256
            != split.dataset_sha256
        ):
            raise ValueError(
                "model signals are bound to a different dataset"
            )

        if (
            split_digest
            != split.split_digest
        ):
            raise ValueError(
                "model signals are bound to a different split"
            )

        expected_indices = np.arange(
            split.sample_count,
            dtype=np.int64,
        )

        if not np.array_equal(
            sample_indices,
            expected_indices,
        ):
            raise ValueError(
                "model signal rows are not in canonical dataset order"
            )

        signals = np.column_stack(
            [
                data["cnn_score"],
                data["cnn_confidence"],
                data["anomaly_score"],
                data["anomaly_confidence"],
            ]
        ).astype(
            np.float32
        )

    if signals.shape != (
        split.sample_count,
        4,
    ):
        raise ValueError(
            "model signals have invalid dimensions"
        )

    if not np.all(
        np.isfinite(
            signals
        )
    ):
        raise ValueError(
            "model signals contain non-finite values"
        )

    if (
        np.any(signals < 0.0)
        or np.any(signals > 1.0)
    ):
        raise ValueError(
            "model signals contain values outside [0, 1]"
        )

    return signals


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create the canonical deterministic "
            "AI train/validation/test split."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--validation-fraction",
        type=float,
        default=0.15,
    )
    parser.add_argument(
        "--test-fraction",
        type=float,
        default=0.15,
    )

    arguments = parser.parse_args()

    _, _, labels = load_dataset(
        arguments.dataset
    )

    split = build_split(
        arguments.dataset,
        labels,
        seed=arguments.seed,
        train_fraction=arguments.train_fraction,
        validation_fraction=(
            arguments.validation_fraction
        ),
        test_fraction=arguments.test_fraction,
    )

    save_split(
        arguments.output,
        split,
    )

    print(
        "Generated:",
        arguments.output,
    )
    print(
        "Dataset SHA-256:",
        split.dataset_sha256,
    )
    print(
        "Split digest:",
        split.split_digest,
    )
    print(
        "TRAIN:",
        len(split.train_indices),
    )
    print(
        "VALIDATION:",
        len(split.validation_indices),
    )
    print(
        "TEST:",
        len(split.test_indices),
    )


if __name__ == "__main__":
    main()
