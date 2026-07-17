"""Fast but physically representative PUF configuration for automated tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.hardware.puf.config import PUFConfig, load_puf_config


def compact_puf_config() -> PUFConfig:
    base = load_puf_config(Path("configs/hardware/puf.json"))
    return replace(
        base,
        ring_oscillator=replace(
            base.ring_oscillator,
            oscillator_count=40,
            response_bits=64,
        ),
        delay_chain=replace(
            base.delay_chain,
            stage_count=32,
            response_bits=64,
        ),
        enrollment=replace(
            base.enrollment,
            challenge_count=4,
            response_samples=5,
            minimum_stable_bit_ratio=0.60,
            corners=(
                (25.0, 1.0),
                (-20.0, 0.95),
                (85.0, 1.05),
                (25.0, 0.90),
                (25.0, 1.10),
            ),
        ),
        authentication=replace(
            base.authentication,
            response_samples=5,
        ),
    )
