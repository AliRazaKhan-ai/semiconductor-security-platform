"""Production PyTorch anomaly detector facade."""

from __future__ import annotations

from pathlib import Path

from app.ai.common import AIModelError, ModelOutput, canonical_hash

from .inference import reconstruction_error
from .loader import load_autoencoder
from .postprocessing import postprocess


class PyTorchAnomalyService:
    def __init__(
        self,
        model_path: Path,
        feature_names: tuple[str, ...],
        version: str = "1.0.0",
        latent_dim: int = 8,
        expected_hash: str | None = None,
        threshold_override: float | None = None,
        scale_override: float | None = None,
    ) -> None:
        if (
            threshold_override is None
        ) != (
            scale_override is None
        ):
            raise ValueError(
                "threshold and scale overrides must be supplied together"
            )

        if (
            threshold_override is not None
            and threshold_override < 0.0
        ):
            raise ValueError(
                "threshold override must be non-negative"
            )

        if (
            scale_override is not None
            and scale_override <= 0.0
        ):
            raise ValueError(
                "scale override must be positive"
            )

        self.model_path = model_path
        self.names = feature_names
        self.version = version
        self.latent_dim = latent_dim
        self.expected_hash = expected_hash
        self.threshold_override = threshold_override
        self.scale_override = scale_override
        self._model = None
        self.threshold: float | None = None
        self.scale: float | None = None
        self.calibration_source: str | None = None

    def infer(
        self,
        features,
    ) -> ModelOutput:
        if self._model is None:
            loaded = load_autoencoder(
                self.model_path,
                len(self.names),
                self.latent_dim,
                self.expected_hash,
            )

            self._model = loaded.model

            if (
                self.threshold_override
                is not None
                and self.scale_override
                is not None
            ):
                self.threshold = (
                    self.threshold_override
                )
                self.scale = (
                    self.scale_override
                )
                self.calibration_source = (
                    "LEGACY_CONFIG_OVERRIDE"
                )
            else:
                self.threshold = (
                    loaded.threshold
                )
                self.scale = (
                    loaded.scale
                )
                self.calibration_source = (
                    "MODEL_ARTIFACT"
                )

        if (
            self.threshold is None
            or self.scale is None
            or self.calibration_source is None
        ):
            raise AIModelError(
                "autoencoder calibration metadata is unavailable"
            )

        error, per_feature = (
            reconstruction_error(
                self._model,
                features,
            )
        )

        result = postprocess(
            error,
            per_feature,
            self.threshold,
            self.scale,
            self.names,
        )

        return ModelOutput(
            "pytorch_autoencoder",
            self.version,
            result["label"],
            result["score"],
            result["confidence"],
            {
                "normal": (
                    1.0
                    - result["score"]
                ),
                "anomalous": (
                    result["score"]
                ),
            },
            {
                "reconstruction_error": (
                    error
                ),
                "threshold": (
                    self.threshold
                ),
                "calibration_source": (
                    self.calibration_source
                ),
                "top_errors": (
                    result["top_errors"]
                ),
            },
            canonical_hash(
                result
            ),
        )
