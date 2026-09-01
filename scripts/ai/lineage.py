"""Fail-closed lineage contracts for controlled AI training runs."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from dataset import (  # noqa: E402
    DatasetSplit,
    load_dataset,
    load_model_signals,
    load_split,
    sha256_file,
)

from app.ai.feature_extraction.schemas import FEATURE_NAMES  # noqa: E402

LINEAGE_SCHEMA_VERSION = "1.0"

TRAINING_SOURCE_PATHS = (
    "scripts/ai/dataset.py",
    "scripts/ai/train_normalizer.py",
    "scripts/ai/train_tensorflow_cnn.py",
    "scripts/ai/train_pytorch_autoencoder.py",
    "scripts/ai/generate_model_signals.py",
    "scripts/ai/train_risk_engine.py",
    "scripts/ai/train_all.sh",
    "scripts/ai/lineage.py",
    "scripts/ai/write_lineage_manifest.py",
)


def _json_digest(
    value: Any,
) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _distribution_version(
    *names: str,
) -> str:
    for name in names:
        try:
            return version(
                name
            )
        except PackageNotFoundError:
            continue

    return "UNAVAILABLE"


def framework_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "tensorflow": _distribution_version(
            "tensorflow",
            "tensorflow-cpu",
        ),
        "torch": _distribution_version(
            "torch"
        ),
        "scikit_learn": _distribution_version(
            "scikit-learn"
        ),
        "numpy": _distribution_version(
            "numpy"
        ),
        "joblib": _distribution_version(
            "joblib"
        ),
    }


def _load_json_object(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            f"{path} must contain a JSON object"
        )

    return value


def _display_path(
    path: Path,
    project_root: Path,
) -> str:
    resolved = path.resolve()

    try:
        return str(
            resolved.relative_to(
                project_root.resolve()
            )
        )
    except ValueError:
        return str(
            resolved
        )


def _require_bound_metrics(
    *,
    name: str,
    path: Path,
    split: DatasetSplit,
    evaluation_split: str | None = None,
    threshold_source: str | None = None,
) -> dict[str, Any]:
    metrics = _load_json_object(
        path
    )

    if (
        metrics.get(
            "dataset_sha256"
        )
        != split.dataset_sha256
    ):
        raise ValueError(
            f"{name} metrics dataset hash mismatch"
        )

    if (
        metrics.get(
            "split_digest"
        )
        != split.split_digest
    ):
        raise ValueError(
            f"{name} metrics split digest mismatch"
        )

    if (
        evaluation_split is not None
        and metrics.get(
            "evaluation_split"
        )
        != evaluation_split
    ):
        raise ValueError(
            f"{name} metrics evaluation split mismatch"
        )

    if (
        threshold_source is not None
        and metrics.get(
            "threshold_source"
        )
        != threshold_source
    ):
        raise ValueError(
            f"{name} threshold source mismatch"
        )

    return metrics


def _artifact_record(
    *,
    project_root: Path,
    artifact_path: Path,
    metrics_path: Path,
    framework: str,
    framework_version: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "framework": framework,
        "framework_version": framework_version,
        "artifact_path": _display_path(
            artifact_path,
            project_root,
        ),
        "artifact_sha256": sha256_file(
            artifact_path
        ),
        "metrics_path": _display_path(
            metrics_path,
            project_root,
        ),
        "metrics_sha256": sha256_file(
            metrics_path
        ),
        "evaluation_contract": {
            key: metrics[key]
            for key in (
                "evaluation_split",
                "threshold_source",
            )
            if key in metrics
        },
    }


def build_lineage_manifest(
    *,
    project_root: Path,
    dataset_path: Path,
    split_path: Path,
    normalizer_path: Path,
    model_signals_path: Path,
    tensorflow_model_path: Path,
    tensorflow_metrics_path: Path,
    pytorch_model_path: Path,
    pytorch_metrics_path: Path,
    risk_model_path: Path,
    risk_metrics_path: Path,
    training_seed: int,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    _, _, labels = load_dataset(
        dataset_path
    )

    split = load_split(
        split_path,
        dataset_path,
        labels,
    )

    load_model_signals(
        model_signals_path,
        split,
    )

    normalizer = _load_json_object(
        normalizer_path
    )

    if tuple(
        normalizer.get(
            "feature_names",
            (),
        )
    ) != FEATURE_NAMES:
        raise ValueError(
            "normalizer feature schema does not match production schema"
        )

    tensorflow_metrics = (
        _require_bound_metrics(
            name="tensorflow",
            path=tensorflow_metrics_path,
            split=split,
            evaluation_split="TEST",
        )
    )

    pytorch_metrics = (
        _require_bound_metrics(
            name="pytorch",
            path=pytorch_metrics_path,
            split=split,
            threshold_source=(
                "CLEAN_VALIDATION"
            ),
        )
    )

    risk_metrics = (
        _require_bound_metrics(
            name="risk",
            path=risk_metrics_path,
            split=split,
            evaluation_split="TEST",
        )
    )

    versions = framework_versions()

    training_sources = {}

    for relative_path in (
        TRAINING_SOURCE_PATHS
    ):
        source = (
            project_root
            / relative_path
        )

        if not source.is_file():
            raise ValueError(
                f"training source is missing: {relative_path}"
            )

        training_sources[
            relative_path
        ] = sha256_file(
            source
        )

    created_at = (
        created_at_utc
        if created_at_utc
        is not None
        else datetime.now(
            UTC
        ).isoformat(
            timespec="seconds"
        )
    )

    payload: dict[str, Any] = {
        "schema_version": (
            LINEAGE_SCHEMA_VERSION
        ),
        "status": (
            "VERIFIED_TRAINING_RUN"
        ),
        "created_at_utc": (
            created_at
        ),
        "dataset": {
            "path": _display_path(
                dataset_path,
                project_root,
            ),
            "sha256": (
                split.dataset_sha256
            ),
            "sample_count": (
                split.sample_count
            ),
        },
        "split": {
            "path": _display_path(
                split_path,
                project_root,
            ),
            "file_sha256": (
                sha256_file(
                    split_path
                )
            ),
            "split_digest": (
                split.split_digest
            ),
            "seed": split.seed,
            "train_fraction": (
                split.train_fraction
            ),
            "validation_fraction": (
                split.validation_fraction
            ),
            "test_fraction": (
                split.test_fraction
            ),
        },
        "normalizer": {
            "path": _display_path(
                normalizer_path,
                project_root,
            ),
            "sha256": (
                sha256_file(
                    normalizer_path
                )
            ),
            "feature_schema_sha256": (
                _json_digest(
                    list(
                        FEATURE_NAMES
                    )
                )
            ),
            "feature_count": (
                len(
                    FEATURE_NAMES
                )
            ),
        },
        "model_signals": {
            "path": _display_path(
                model_signals_path,
                project_root,
            ),
            "sha256": (
                sha256_file(
                    model_signals_path
                )
            ),
            "dataset_sha256": (
                split.dataset_sha256
            ),
            "split_digest": (
                split.split_digest
            ),
        },
        "models": {
            "tensorflow": (
                _artifact_record(
                    project_root=project_root,
                    artifact_path=(
                        tensorflow_model_path
                    ),
                    metrics_path=(
                        tensorflow_metrics_path
                    ),
                    framework=(
                        "tensorflow"
                    ),
                    framework_version=(
                        versions[
                            "tensorflow"
                        ]
                    ),
                    metrics=(
                        tensorflow_metrics
                    ),
                )
            ),
            "pytorch": (
                _artifact_record(
                    project_root=project_root,
                    artifact_path=(
                        pytorch_model_path
                    ),
                    metrics_path=(
                        pytorch_metrics_path
                    ),
                    framework="torch",
                    framework_version=(
                        versions[
                            "torch"
                        ]
                    ),
                    metrics=(
                        pytorch_metrics
                    ),
                )
            ),
            "risk_engine": (
                _artifact_record(
                    project_root=project_root,
                    artifact_path=(
                        risk_model_path
                    ),
                    metrics_path=(
                        risk_metrics_path
                    ),
                    framework=(
                        "scikit-learn"
                    ),
                    framework_version=(
                        versions[
                            "scikit_learn"
                        ]
                    ),
                    metrics=(
                        risk_metrics
                    ),
                )
            ),
        },
        "training": {
            "seed": int(
                training_seed
            ),
            "framework_versions": (
                versions
            ),
            "source_sha256": (
                training_sources
            ),
        },
    }

    if (
        int(training_seed)
        != split.seed
    ):
        raise ValueError(
            "training seed does not match canonical split seed"
        )

    payload["lineage_digest"] = (
        _json_digest(
            payload
        )
    )

    return payload


def verify_lineage_manifest(
    payload: dict[str, Any],
) -> None:
    stored_digest = str(
        payload.get(
            "lineage_digest",
            "",
        )
    )

    if not stored_digest:
        raise ValueError(
            "lineage manifest lacks lineage digest"
        )

    unsigned = dict(
        payload
    )

    unsigned.pop(
        "lineage_digest",
        None,
    )

    expected = _json_digest(
        unsigned
    )

    if stored_digest != expected:
        raise ValueError(
            "lineage manifest digest verification failed"
        )


def write_lineage_manifest(
    path: Path,
    payload: dict[str, Any],
) -> None:
    verify_lineage_manifest(
        payload
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        f".{path.name}.tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(
        path
    )


def load_lineage_manifest(
    path: Path,
) -> dict[str, Any]:
    payload = _load_json_object(
        path
    )

    verify_lineage_manifest(
        payload
    )

    return payload
