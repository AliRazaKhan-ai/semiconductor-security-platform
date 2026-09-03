"""Compose the production AI services from validated platform configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai import AIPipelineService
from app.ai.feature_extraction import FeatureExtractionService
from app.ai.feature_extraction.schemas import FEATURE_SCHEMAS
from app.ai.feature_extraction.normalization import RobustNormalizer
from app.ai.pytorch_anomaly import PyTorchAnomalyService
from app.ai.risk_engine import RiskEngineService
from app.ai.tensorflow_classifier import TensorFlowClassifierService


def _resolve(
    root: Path,
    value: str,
) -> Path:
    path = Path(
        value
    )

    return (
        path
        if path.is_absolute()
        else root / path
    )


def build_ai_pipeline(
    project_root: Path,
    config: dict[str, Any],
) -> AIPipelineService:
    tensorflow_config = dict(
        config["tensorflow"]
    )
    pytorch_config = dict(
        config["pytorch"]
    )
    risk_config = dict(
        config["risk_engine"]
    )

    # ai.schema_version selects the production feature schema. It previously
    # declared a version while every consumer imported the v1.0 constant directly,
    # so the key was inert: changing it changed nothing and a schema migration
    # surfaced as a shape error rather than a configuration statement.
    schema_version = str(
        config.get(
            "schema_version",
            "1.0",
        )
    )

    if schema_version not in FEATURE_SCHEMAS:
        raise ValueError(
            f"ai.schema_version {schema_version!r} is not registered in "
            f"FEATURE_SCHEMAS; known versions are "
            f"{sorted(FEATURE_SCHEMAS)}"
        )

    feature_names = tuple(
        FEATURE_SCHEMAS[
            schema_version
        ]
    )

    normalizer = RobustNormalizer.load(
        _resolve(
            project_root,
            str(
                config[
                    "normalizer_path"
                ]
            ),
        )
    )

    if (
        tuple(
            normalizer.feature_names
        )
        != feature_names
    ):
        raise ValueError(
            "normalizer feature schema does not match production schema "
            f"{schema_version}: normalizer has "
            f"{len(normalizer.feature_names)} features, schema declares "
            f"{len(feature_names)}"
        )

    cnn = TensorFlowClassifierService(
        _resolve(
            project_root,
            str(
                tensorflow_config[
                    "model_path"
                ]
            ),
        ),
        tuple(
            tensorflow_config[
                "labels"
            ]
        ),
        str(
            tensorflow_config.get(
                "version",
                "1.0.0",
            )
        ),
        tensorflow_config.get(
            "sha256"
        ),
        float(
            tensorflow_config.get(
                "min_confidence",
                0.60,
            )
        ),
    )

    threshold_override = (
        float(
            pytorch_config[
                "threshold"
            ]
        )
        if "threshold"
        in pytorch_config
        else None
    )

    scale_override = (
        float(
            pytorch_config[
                "scale"
            ]
        )
        if "scale"
        in pytorch_config
        else None
    )

    anomaly = PyTorchAnomalyService(
        _resolve(
            project_root,
            str(
                pytorch_config[
                    "model_path"
                ]
            ),
        ),
        feature_names,
        version=str(
            pytorch_config.get(
                "version",
                "1.0.0",
            )
        ),
        latent_dim=int(
            pytorch_config.get(
                "latent_dim",
                8,
            )
        ),
        expected_hash=(
            pytorch_config.get(
                "sha256"
            )
        ),
        threshold_override=(
            threshold_override
        ),
        scale_override=(
            scale_override
        ),
    )

    risk_service = RiskEngineService(
        _resolve(
            project_root,
            str(
                risk_config[
                    "model_path"
                ]
            ),
        ),
        feature_names,
        str(
            risk_config.get(
                "version",
                "1.0.0",
            )
        ),
        risk_config.get(
            "sha256"
        ),
    )

    return AIPipelineService(
        # The extractor is constructed with the declared schema rather than the
        # default, so _active_feature_schema can read the running schema back from
        # service.features.feature_names and the contract check cannot disagree
        # with the model that is actually loaded.
        FeatureExtractionService(
            int(
                config.get(
                    "sequence_length",
                    256,
                )
            ),
            feature_names=feature_names,
        ),
        normalizer,
        cnn,
        anomaly,
        risk_service,
    )
