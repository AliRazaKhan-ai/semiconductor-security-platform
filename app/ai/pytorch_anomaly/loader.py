"""PyTorch autoencoder architecture and integrity-checked artifact loading."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.ai.common import AIModelError


@dataclass(frozen=True, slots=True)
class LoadedAutoencoder:
    model: Any
    threshold: float
    scale: float


def build_autoencoder(
    input_dim: int,
    latent_dim: int = 8,
):
    try:
        import torch.nn as nn
    except ImportError as exc:
        raise AIModelError(
            "PyTorch is not installed"
        ) from exc

    class Autoencoder(nn.Module):
        def __init__(self):
            super().__init__()

            hidden = max(
                16,
                input_dim // 2,
            )

            self.encoder = nn.Sequential(
                nn.Linear(
                    input_dim,
                    hidden,
                ),
                nn.LayerNorm(
                    hidden
                ),
                nn.GELU(),
                nn.Linear(
                    hidden,
                    latent_dim,
                ),
            )

            self.decoder = nn.Sequential(
                nn.Linear(
                    latent_dim,
                    hidden,
                ),
                nn.GELU(),
                nn.Linear(
                    hidden,
                    input_dim,
                ),
            )

        def forward(self, x):
            return self.decoder(
                self.encoder(x)
            )

    return Autoencoder()


def _hash(
    path: Path,
) -> str:
    digest = sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def load_autoencoder(
    path: Path,
    input_dim: int,
    latent_dim: int = 8,
    expected_hash: str | None = None,
) -> LoadedAutoencoder:
    if not path.is_file():
        raise AIModelError(
            f"PyTorch model not found: {path}"
        )

    if (
        expected_hash
        and _hash(path)
        != expected_hash
    ):
        raise AIModelError(
            "PyTorch model integrity verification failed"
        )

    try:
        import torch
    except ImportError as exc:
        raise AIModelError(
            "PyTorch is not installed"
        ) from exc

    payload = torch.load(
        path,
        map_location="cpu",
        weights_only=True,
    )

    required = {
        "state_dict",
        "input_dim",
        "threshold",
        "scale",
    }

    if not isinstance(
        payload,
        dict,
    ) or not required.issubset(
        payload
    ):
        raise AIModelError(
            "PyTorch autoencoder artifact lacks required calibration metadata"
        )

    artifact_input_dim = int(
        payload["input_dim"]
    )

    if (
        artifact_input_dim
        != input_dim
    ):
        raise AIModelError(
            "PyTorch autoencoder input dimension mismatch"
        )

    threshold = float(
        payload["threshold"]
    )

    scale = float(
        payload["scale"]
    )

    if (
        threshold < 0.0
        or scale <= 0.0
    ):
        raise AIModelError(
            "PyTorch autoencoder calibration metadata is invalid"
        )

    model = build_autoencoder(
        input_dim,
        latent_dim,
    )

    model.load_state_dict(
        payload["state_dict"]
    )

    model.eval()

    return LoadedAutoencoder(
        model=model,
        threshold=threshold,
        scale=scale,
    )
