"""Compose the production AI services from validated platform configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai import AIPipelineService
from app.ai.feature_extraction import FEATURE_NAMES, FeatureExtractionService
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
        != FEATURE_NAMES
    ):
        raise ValueError(
            "normalizer feature schema does not match production schema"
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
        FEATURE_NAMES,
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
        FEATURE_NAMES,
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
        FeatureExtractionService(
            int(
                config.get(
                    "sequence_length",
                    256,
                )
            )
        ),
        normalizer,
        cnn,
        anomaly,
        risk_service,
    )
