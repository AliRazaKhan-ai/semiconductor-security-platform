#!/usr/bin/env python3
"""Fit the production robust normalizer using canonical training rows only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
    ),
)

from dataset import load_dataset, load_split

from corpus_schema import resolve_feature_names

from app.ai.feature_extraction.normalization import RobustNormalizer


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
        "--output",
        type=Path,
        required=True,
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

    train_indices = np.asarray(
        split.train_indices,
        dtype=np.int64,
    )

    # The corpus declares the schema it was generated against, so the normalizer
    # is always fitted to the names the data actually has.
    feature_names, source = resolve_feature_names(
        arguments.dataset
    )

    print(
        f"schema: {len(feature_names)} features via {source}"
    )

    RobustNormalizer.fit(
        features[train_indices],
        feature_names,
    ).save(
        arguments.output
    )


if __name__ == "__main__":
    main()
