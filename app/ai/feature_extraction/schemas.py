"""Typed contracts for physical, design, supply-chain, and model-ready features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

FEATURE_SCHEMA_VERSION = "1.0"

FEATURE_NAMES = (
    "power_mean",
    "power_std",
    "power_rms",
    "power_peak_to_peak",
    "power_crest_factor",
    "power_skewness",
    "power_kurtosis",
    "power_spectral_entropy",
    "em_mean",
    "em_std",
    "em_rms",
    "em_peak_to_peak",
    "em_spectral_entropy",
    "timing_mean",
    "timing_std",
    "timing_jitter",
    "gate_count_log",
    "cell_type_diversity",
    "unused_logic_ratio",
    "rare_net_ratio",
    "sequential_ratio",
    "combinational_ratio",
    "netlist_delta_ratio",
    "simulation_failure_ratio",
    "supplier_risk",
    "country_risk",
    "custody_gap_ratio",
    "certificate_risk",
    "sbom_mismatch_ratio",
    "threat_intel_score",
    "puf_instability",
    "opentitan_risk",
)


CANDIDATE_FEATURE_SCHEMA_VERSION = "2.0"

CANDIDATE_FEATURE_NAMES = (
    "power_mean",
    "power_std",
    "power_rms",
    "power_peak_to_peak",
    "power_crest_factor",
    "power_skewness",
    "power_kurtosis",
    "power_spectral_entropy",
    "em_mean",
    "em_std",
    "em_rms",
    "em_peak_to_peak",
    "em_spectral_entropy",
    "timing_mean",
    "timing_std",
    "timing_jitter",
    "cell_count_log",
    "wire_count_log",
    "wire_bit_count_log",
    "public_wire_ratio",
    "cell_type_diversity",
    "sequential_ratio",
    "combinational_ratio",
    "memory_bit_count_log",
    "supplier_risk",
    "country_risk",
    "custody_gap_ratio",
    "certificate_risk",
    "sbom_mismatch_ratio",
    "threat_intel_score",
    "puf_instability",
    "opentitan_risk",
)


@dataclass(frozen=True, slots=True)
class FeatureVector:
    names: tuple[str, ...]
    values: tuple[float, ...]
    sequence: tuple[tuple[float, float, float], ...]
    metadata: dict[str, Any]

    def to_array(self) -> np.ndarray:
        return np.asarray(
            self.values,
            dtype=np.float32,
        )

    def sequence_array(self) -> np.ndarray:
        return np.asarray(
            self.sequence,
            dtype=np.float32,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
