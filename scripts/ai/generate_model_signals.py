#!/usr/bin/env python3
"""
Generate model_signals.npz from the trained TensorFlow CNN and PyTorch
autoencoder.

Outputs:
    cnn_score             Probability that a sample is non-clean.
    cnn_confidence        Confidence of the CNN's predicted class.
    anomaly_score         Calibrated autoencoder anomaly probability.
    anomaly_confidence    Confidence based on distance from the threshold.

The output rows preserve exactly the same order as the source dataset.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset import load_dataset, load_split  # noqa: E402

from app.ai.feature_extraction.normalization import RobustNormalizer  # noqa: E402
from app.ai.feature_extraction.schemas import FEATURE_NAMES  # noqa: E402
from app.ai.pytorch_anomaly.loader import build_autoencoder  # noqa: E402


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CNN and autoencoder signals for risk-engine training."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="NPZ dataset containing features, sequences and labels.",
    )
    parser.add_argument(
        "--split",
        type=Path,
        required=True,
        help="Canonical dataset split JSON.",
    )
    parser.add_argument(
        "--normalizer",
        type=Path,
        required=True,
        help="Persisted production feature normalizer.",
    )
    parser.add_argument(
        "--tensorflow-model",
        type=Path,
        required=True,
        help="Trained TensorFlow CNN .keras model.",
    )
    parser.add_argument(
        "--pytorch-model",
        type=Path,
        required=True,
        help="Trained PyTorch autoencoder .pt model.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination model_signals.npz file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Inference batch size.",
    )
    return parser.parse_args()


def normalized_entropy(probabilities: np.ndarray) -> np.ndarray:
    """Return normalized entropy in the inclusive range [0, 1]."""
    class_count = probabilities.shape[1]

    if class_count < 2:
        raise ValueError("CNN output must contain at least two classes.")

    safe = np.clip(probabilities, 1e-12, 1.0)
    entropy = -np.sum(safe * np.log(safe), axis=1)
    return entropy / math.log(class_count)


def calculate_cnn_signals(
    sequences: np.ndarray,
    model_path: Path,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Run CNN inference.

    cnn_score:
        1 - probability(CLEAN), where class index 0 represents CLEAN.

    cnn_confidence:
        Combination of top probability, top-two margin and inverse entropy.
        This matches the production CNN post-processing logic.
    """
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise RuntimeError("TensorFlow is not installed.") from exc

    if not model_path.is_file():
        raise FileNotFoundError(f"TensorFlow model not found: {model_path}")

    model = tf.keras.models.load_model(model_path, compile=False)

    probabilities = np.asarray(
        model.predict(
            sequences,
            batch_size=batch_size,
            verbose=1,
        ),
        dtype=np.float64,
    )

    if probabilities.ndim != 2:
        raise ValueError(
            f"TensorFlow output must be two-dimensional, got {probabilities.shape}."
        )

    if probabilities.shape[0] != sequences.shape[0]:
        raise ValueError("TensorFlow output row count differs from dataset length.")

    if probabilities.shape[1] < 2:
        raise ValueError("TensorFlow model must output at least two classes.")

    if not np.all(np.isfinite(probabilities)):
        raise ValueError("TensorFlow model produced non-finite probabilities.")

    row_sums = probabilities.sum(axis=1, keepdims=True)
    requires_softmax = (
        np.any(probabilities < 0.0)
        or np.any(np.abs(row_sums - 1.0) > 1e-3)
    )

    if requires_softmax:
        shifted = probabilities - probabilities.max(axis=1, keepdims=True)
        exponentials = np.exp(shifted)
        probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)

    clean_probability = probabilities[:, 0]
    cnn_score = 1.0 - clean_probability

    ordered = np.sort(probabilities, axis=1)
    top_probability = ordered[:, -1]
    top_two_margin = ordered[:, -1] - ordered[:, -2]
    entropy = normalized_entropy(probabilities)

    cnn_confidence = (
        0.55 * top_probability
        + 0.30 * top_two_margin
        + 0.15 * (1.0 - entropy)
    )

    return (
        np.clip(cnn_score, 0.0, 1.0).astype(np.float32),
        np.clip(cnn_confidence, 0.0, 1.0).astype(np.float32),
    )


def sigmoid(values: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    bounded = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-bounded))


def calculate_anomaly_signals(
    features: np.ndarray,
    model_path: Path,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Run PyTorch autoencoder inference.

    anomaly_score:
        Sigmoid-calibrated reconstruction error relative to the learned
        clean-sample threshold.

    anomaly_confidence:
        Confidence increases as reconstruction error moves farther away
        from the threshold in either direction.
    """
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is not installed.") from exc

    if not model_path.is_file():
        raise FileNotFoundError(f"PyTorch model not found: {model_path}")

    payload = torch.load(
        model_path,
        map_location="cpu",
        weights_only=True,
    )

    required_keys = {"state_dict", "input_dim", "threshold", "scale"}
    missing_keys = required_keys.difference(payload)

    if missing_keys:
        raise ValueError(
            f"PyTorch model payload is missing keys: {sorted(missing_keys)}"
        )

    input_dimension = int(payload["input_dim"])
    threshold = float(payload["threshold"])
    scale = max(float(payload["scale"]), 1e-8)
    latent_dimension = max(4, input_dimension // 4)

    if features.shape[1] != input_dimension:
        raise ValueError(
            "Dataset feature dimension does not match the autoencoder: "
            f"{features.shape[1]} != {input_dimension}"
        )

    model = build_autoencoder(
        input_dim=input_dimension,
        latent_dim=latent_dimension,
    )
    model.load_state_dict(payload["state_dict"])
    model.eval()

    reconstruction_errors: list[np.ndarray] = []

    with torch.inference_mode():
        for start in range(0, len(features), batch_size):
            end = min(start + batch_size, len(features))

            batch = torch.as_tensor(
                features[start:end],
                dtype=torch.float32,
            )

            reconstructed = model(batch)
            errors = ((reconstructed - batch) ** 2).mean(dim=1)
            reconstruction_errors.append(errors.cpu().numpy())

    error_values = np.concatenate(reconstruction_errors).astype(np.float64)

    if len(error_values) != len(features):
        raise ValueError("Autoencoder output row count differs from dataset length.")

    if not np.all(np.isfinite(error_values)):
        raise ValueError("Autoencoder produced non-finite reconstruction errors.")

    standardized_distance = (error_values - threshold) / scale
    anomaly_score = sigmoid(standardized_distance)

    absolute_distance = np.abs(error_values - threshold) / scale
    anomaly_confidence = 1.0 - np.exp(-absolute_distance)

    return (
        np.clip(anomaly_score, 0.0, 1.0).astype(np.float32),
        np.clip(anomaly_confidence, 0.0, 1.0).astype(np.float32),
    )


def validate_signals(
    sample_count: int,
    cnn_score: np.ndarray,
    cnn_confidence: np.ndarray,
    anomaly_score: np.ndarray,
    anomaly_confidence: np.ndarray,
) -> None:
    arrays = {
        "cnn_score": cnn_score,
        "cnn_confidence": cnn_confidence,
        "anomaly_score": anomaly_score,
        "anomaly_confidence": anomaly_confidence,
    }

    for name, values in arrays.items():
        if values.shape != (sample_count,):
            raise ValueError(
                f"{name} must have shape ({sample_count},), got {values.shape}."
            )

        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} contains non-finite values.")

        if np.any(values < 0.0) or np.any(values > 1.0):
            raise ValueError(f"{name} contains values outside [0, 1].")


def main() -> None:
    arguments = parse_arguments()

    if arguments.batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")

    features, sequences, labels = load_dataset(arguments.dataset)
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

    cnn_score, cnn_confidence = calculate_cnn_signals(
        sequences=sequences,
        model_path=arguments.tensorflow_model,
        batch_size=arguments.batch_size,
    )

    anomaly_score, anomaly_confidence = calculate_anomaly_signals(
        features=normalized_features,
        model_path=arguments.pytorch_model,
        batch_size=arguments.batch_size,
    )

    validate_signals(
        sample_count=len(labels),
        cnn_score=cnn_score,
        cnn_confidence=cnn_confidence,
        anomaly_score=anomaly_score,
        anomaly_confidence=anomaly_confidence,
    )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        arguments.output,
        cnn_score=cnn_score,
        cnn_confidence=cnn_confidence,
        anomaly_score=anomaly_score,
        anomaly_confidence=anomaly_confidence,
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

    print(f"Generated: {arguments.output}")
    print(f"Samples: {len(labels)}")
    print(f"CNN risk mean: {float(cnn_score.mean()):.6f}")
    print(f"CNN confidence mean: {float(cnn_confidence.mean()):.6f}")
    print(f"Anomaly score mean: {float(anomaly_score.mean()):.6f}")
    print(
        "Anomaly confidence mean: "
        f"{float(anomaly_confidence.mean()):.6f}"
    )


if __name__ == "__main__":
    main()
