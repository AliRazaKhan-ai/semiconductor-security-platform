#!/usr/bin/env python3
"""Train, validate and test the temporal CNN using one canonical split."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
from dataset import load_dataset, load_split


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
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    arguments = parser.parse_args()

    import tensorflow as tf

    random.seed(
        arguments.seed
    )
    np.random.seed(
        arguments.seed
    )
    tf.random.set_seed(
        arguments.seed
    )

    _, sequences, labels = load_dataset(
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
    validation_indices = np.asarray(
        split.validation_indices,
        dtype=np.int64,
    )
    test_indices = np.asarray(
        split.test_indices,
        dtype=np.int64,
    )

    classes = int(
        labels[train_indices].max()
        + 1
    )

    inputs = tf.keras.Input(
        shape=sequences.shape[1:]
    )

    layer = tf.keras.layers.Conv1D(
        32,
        7,
        padding="same",
        activation="relu",
    )(
        inputs
    )
    layer = tf.keras.layers.BatchNormalization()(
        layer
    )
    layer = tf.keras.layers.MaxPool1D(
        2
    )(
        layer
    )
    layer = tf.keras.layers.Conv1D(
        64,
        5,
        padding="same",
        activation="relu",
    )(
        layer
    )
    layer = tf.keras.layers.BatchNormalization()(
        layer
    )
    layer = tf.keras.layers.GlobalAveragePooling1D()(
        layer
    )
    layer = tf.keras.layers.Dropout(
        0.25
    )(
        layer
    )
    outputs = tf.keras.layers.Dense(
        classes,
        activation="softmax",
    )(
        layer
    )

    model = tf.keras.Model(
        inputs,
        outputs,
    )

    model.compile(
        optimizer=tf.keras.optimizers.Adam(
            1e-3
        ),
        loss="sparse_categorical_crossentropy",
        metrics=[
            "accuracy",
        ],
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            patience=8,
            restore_best_weights=True,
            monitor="val_loss",
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            patience=4,
            factor=0.5,
        ),
    ]

    history = model.fit(
        sequences[train_indices],
        labels[train_indices],
        validation_data=(
            sequences[validation_indices],
            labels[validation_indices],
        ),
        epochs=arguments.epochs,
        batch_size=arguments.batch_size,
        callbacks=callbacks,
        verbose=2,
    )

    metrics = model.evaluate(
        sequences[test_indices],
        labels[test_indices],
        verbose=0,
        return_dict=True,
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    model.save(
        arguments.output
    )

    metrics_payload = {
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
        "metrics": metrics,
        "history": history.history,
    }

    arguments.output.with_suffix(
        ".metrics.json"
    ).write_text(
        json.dumps(
            metrics_payload,
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
