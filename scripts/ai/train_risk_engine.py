#!/usr/bin/env python3
"""Train and evaluate the risk classifier using the canonical AI split."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
    ),
)
from dataset import (
    load_dataset,
    load_model_signals,
    load_split,
)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
)

from app.ai.feature_extraction.normalization import RobustNormalizer  # noqa: E402
from corpus_schema import require_matching_normalizer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--split",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--normalizer",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--model-signals",
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

    arguments = parser.parse_args()

    features, _, labels = load_dataset(
        arguments.dataset
    )

    split = load_split(
        arguments.split,
        arguments.dataset,
        labels,
    )

    signals = load_model_signals(
        arguments.model_signals,
        split,
    )

    normalizer = RobustNormalizer.load(
        arguments.normalizer
    )

    require_matching_normalizer(
        normalizer.feature_names,
        arguments.dataset,
    )

    normalized_features = (
        normalizer.transform(
            features
        )
    )

    combined = np.column_stack(
        [
            normalized_features,
            signals,
        ]
    )

    target = (
        labels > 0
    ).astype(
        np.int64
    )

    train_indices = np.asarray(
        split.train_indices,
        dtype=np.int64,
    )

    test_indices = np.asarray(
        split.test_indices,
        dtype=np.int64,
    )

    base = RandomForestClassifier(
        n_estimators=500,
        max_depth=14,
        min_samples_leaf=3,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=arguments.seed,
    )

    model = CalibratedClassifierCV(
        base,
        method="sigmoid",
        cv=5,
    )

    model.fit(
        combined[train_indices],
        target[train_indices],
    )

    predictions = model.predict(
        combined[test_indices]
    )

    probabilities = (
        model.predict_proba(
            combined[test_indices]
        )[:, 1]
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        arguments.output,
    )

    metrics = {
        "evaluation_split": "TEST",
        "dataset_sha256": split.dataset_sha256,
        "split_digest": split.split_digest,
        "train_samples": len(
            split.train_indices
        ),
        "validation_samples": len(
            split.validation_indices
        ),
        "test_samples": len(
            split.test_indices
        ),
        "roc_auc": roc_auc_score(
            target[test_indices],
            probabilities,
        ),
        "classification_report": (
            classification_report(
                target[test_indices],
                predictions,
                output_dict=True,
                zero_division=0,
            )
        ),
    }

    arguments.output.with_suffix(
        ".metrics.json"
    ).write_text(
        json.dumps(
            metrics,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
