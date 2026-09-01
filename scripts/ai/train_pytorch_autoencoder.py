#!/usr/bin/env python3
"""Train the autoencoder on canonical clean training rows only."""

from __future__ import annotations

import argparse
import json
import random
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

from app.ai.feature_extraction.normalization import RobustNormalizer
from app.ai.feature_extraction.schemas import FEATURE_NAMES
from app.ai.pytorch_anomaly.loader import build_autoencoder


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
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    arguments = parser.parse_args()

    import torch

    random.seed(
        arguments.seed
    )
    np.random.seed(
        arguments.seed
    )
    torch.manual_seed(
        arguments.seed
    )

    features, _, labels = load_dataset(
        arguments.dataset
    )

    split = load_split(
        arguments.split,
        arguments.dataset,
        labels,
    )

    normalizer = RobustNormalizer.load(
        arguments.normalizer
    )

    if (
        tuple(normalizer.feature_names)
        != FEATURE_NAMES
    ):
        raise ValueError(
            "normalizer feature schema does not match training schema"
        )

    normalized_features = (
        normalizer.transform(
            features
        )
    )

    train_indices = np.asarray(
        split.train_indices,
        dtype=np.int64,
    )
    validation_indices = np.asarray(
        split.validation_indices,
        dtype=np.int64,
    )

    train_features = normalized_features[
        train_indices
    ]
    train_labels = labels[
        train_indices
    ]

    validation_features = normalized_features[
        validation_indices
    ]
    validation_labels = labels[
        validation_indices
    ]

    clean_train = train_features[
        train_labels == 0
    ]

    clean_validation = (
        validation_features[
            validation_labels == 0
        ]
    )

    if len(clean_train) < 20:
        raise ValueError(
            "at least 20 clean training samples are required"
        )

    if len(clean_validation) < 20:
        raise ValueError(
            "at least 20 clean validation samples are required"
        )

    training_tensor = torch.tensor(
        clean_train,
        dtype=torch.float32,
    )

    validation_tensor = torch.tensor(
        clean_validation,
        dtype=torch.float32,
    )

    loader = torch.utils.data.DataLoader(
        training_tensor,
        batch_size=arguments.batch_size,
        shuffle=True,
    )

    latent_dimension = max(
        4,
        features.shape[1] // 4,
    )

    model = build_autoencoder(
        features.shape[1],
        latent_dimension,
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=1e-3,
        weight_decay=1e-5,
    )

    loss_function = torch.nn.MSELoss()

    model.train()

    for _ in range(
        arguments.epochs
    ):
        for batch in loader:
            optimizer.zero_grad()

            loss = loss_function(
                model(batch),
                batch,
            )

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                model.parameters(),
                1.0,
            )

            optimizer.step()

    model.eval()

    with torch.inference_mode():
        validation_errors = (
            (
                model(
                    validation_tensor
                )
                - validation_tensor
            )
            ** 2
        ).mean(
            dim=1
        ).numpy()

    threshold = float(
        np.quantile(
            validation_errors,
            0.995,
        )
    )

    scale = float(
        max(
            np.std(
                validation_errors
            ),
            1e-8,
        )
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": features.shape[1],
            "threshold": threshold,
            "scale": scale,
        },
        arguments.output,
    )

    metrics = {
        "threshold_source": (
            "CLEAN_VALIDATION"
        ),
        "dataset_sha256": (
            split.dataset_sha256
        ),
        "split_digest": (
            split.split_digest
        ),
        "clean_training_samples": len(
            clean_train
        ),
        "clean_validation_samples": len(
            clean_validation
        ),
        "threshold": threshold,
        "scale": scale,
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
