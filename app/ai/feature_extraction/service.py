"""Coordinate all deterministic feature extractors and produce one model contract."""
from __future__ import annotations
from typing import Any
from app.ai.common import canonical_hash
from .schemas import FEATURE_NAMES, FeatureVector
from .physical_features import extract_physical
from .design_features import extract_design
from .supply_chain_features import extract_supply_chain

class FeatureExtractionService:
    def __init__(self, sequence_length: int=256): self.sequence_length=sequence_length
    def extract(self,evidence: dict[str,Any]) -> FeatureVector:
        physical,seq=extract_physical(dict(evidence.get("side_channel",evidence)),self.sequence_length)
        values={**physical,**extract_design(evidence),**extract_supply_chain(evidence)}
        missing=[n for n in FEATURE_NAMES if n not in values]
        if missing: raise ValueError(f"feature extractor missing: {missing}")
        ordered=tuple(float(values[n]) for n in FEATURE_NAMES)
        metadata={"schema_version":"1.0","sequence_length":self.sequence_length,"feature_hash":canonical_hash(dict(zip(FEATURE_NAMES,ordered)))}
        return FeatureVector(FEATURE_NAMES,ordered,tuple(tuple(map(float,row)) for row in seq),metadata)
