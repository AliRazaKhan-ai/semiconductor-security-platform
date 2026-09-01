#!/usr/bin/env python3
"""Generate the fail-closed AI training-run lineage manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from lineage import (
    build_lineage_manifest,
    write_lineage_manifest,
)


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
        "--tensorflow-model",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--tensorflow-metrics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--pytorch-model",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--pytorch-metrics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--risk-model",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--risk-metrics",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    arguments = parser.parse_args()

    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    payload = build_lineage_manifest(
        project_root=project_root,
        dataset_path=arguments.dataset,
        split_path=arguments.split,
        normalizer_path=(
            arguments.normalizer
        ),
        model_signals_path=(
            arguments.model_signals
        ),
        tensorflow_model_path=(
            arguments.tensorflow_model
        ),
        tensorflow_metrics_path=(
            arguments.tensorflow_metrics
        ),
        pytorch_model_path=(
            arguments.pytorch_model
        ),
        pytorch_metrics_path=(
            arguments.pytorch_metrics
        ),
        risk_model_path=(
            arguments.risk_model
        ),
        risk_metrics_path=(
            arguments.risk_metrics
        ),
        training_seed=(
            arguments.seed
        ),
    )

    write_lineage_manifest(
        arguments.output,
        payload,
    )

    print(
        "Generated:",
        arguments.output,
    )
    print(
        "Status:",
        payload["status"],
    )
    print(
        "Dataset SHA-256:",
        payload[
            "dataset"
        ]["sha256"],
    )
    print(
        "Split digest:",
        payload[
            "split"
        ]["split_digest"],
    )
    print(
        "Lineage digest:",
        payload[
            "lineage_digest"
        ],
    )


if __name__ == "__main__":
    main()
