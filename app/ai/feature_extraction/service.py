"""Coordinate deterministic feature extractors and produce a selected model contract."""

from __future__ import annotations

from typing import Any

from app.ai.common import canonical_hash

from .design_features import extract_design
from .physical_features import extract_physical
from .schemas import FEATURE_NAMES, FeatureVector
from .supply_chain_features import extract_supply_chain


class FeatureExtractionService:
    def __init__(
        self,
        sequence_length: int = 256,
        feature_names: tuple[str, ...] = FEATURE_NAMES,
    ):
        self.sequence_length = sequence_length
        self.feature_names = tuple(
            feature_names
        )

        if not self.feature_names:
            raise ValueError(
                "feature schema must not be empty"
            )

        if len(
            set(
                self.feature_names
            )
        ) != len(
            self.feature_names
        ):
            raise ValueError(
                "feature schema contains duplicate names"
            )

    def extract(
        self,
        evidence: dict[str, Any],
    ) -> FeatureVector:
        physical, sequence = extract_physical(
            dict(
                evidence.get(
                    "side_channel",
                    evidence,
                )
            ),
            self.sequence_length,
        )

        values = {
            **physical,
            **extract_design(
                evidence
            ),
            **extract_supply_chain(
                evidence
            ),
        }

        missing = [
            name
            for name
            in self.feature_names
            if name
            not in values
        ]

        if missing:
            raise ValueError(
                f"feature extractor missing: {missing}"
            )

        ordered = tuple(
            float(
                values[name]
            )
            for name
            in self.feature_names
        )

        metadata = {
            "schema_version": "1.0",
            "sequence_length": (
                self.sequence_length
            ),
            "feature_count": len(
                self.feature_names
            ),
            "feature_schema_hash": (
                canonical_hash(
                    list(
                        self.feature_names
                    )
                )
            ),
            "feature_hash": canonical_hash(
                dict(
                    zip(
                        self.feature_names,
                        ordered,
                        strict=True,
                    )
                )
            ),
        }

        return FeatureVector(
            self.feature_names,
            ordered,
            tuple(
                tuple(
                    map(
                        float,
                        row,
                    )
                )
                for row
                in sequence
            ),
            metadata,
        )
