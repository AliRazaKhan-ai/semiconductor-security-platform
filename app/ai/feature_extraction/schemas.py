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


# --- v2.1 (candidate-plus) ------------------------------------------------
#
# CANDIDATE_FEATURE_NAMES (v2.0) substituted eight absolute Yosys statistics for the
# eight v1.0 design features, because the hardware pipeline can read cell, wire and
# memory counts directly from `yosys stat -json` but cannot supply the v1.0 set.
#
# That substitution removed every reference-relative structural feature. A hardware
# Trojan is not characterised by a design being large; it is characterised by a design
# differing from its known-good reference. v2.1 restores the two relative features that
# are computable from code already present in this repository:
#
#   netlist_delta_ratio       app/hardware/yosys/rules.py::structural_delta_summary(),
#                             candidate netlist against hardware_lab/rtl/reference/
#   simulation_failure_ratio  app/hardware/verilator/result_parser.py, failed assertions
#                             over total assertions
#
# Deliberately NOT restored, and declared as a known gap:
#
#   unused_logic_ratio        requires a second synthesis pass and an `opt_clean -purge`
#                             cell-count delta
#   rare_net_ratio            requires static signal-probability and controllability
#                             analysis (SCOAP-style), which is not implemented here
#
# Both are obtainable by established methods. Neither is built. This is a scope decision,
# not a claim of infeasibility.
#
# Physical features 0-15 and supply-chain features 26-33 are identical to v1.0 and v2.0.
# Both restored names are already produced by extract_design(); no extractor changes are
# required by this schema. However, both default to 0.0 when their source key is absent
# from the evidence dictionary, so netlist_delta_ratio MUST be surfaced into the AI
# evidence contract before any model is trained against this schema.

CANDIDATE_PLUS_FEATURE_SCHEMA_VERSION = "2.1"
CANDIDATE_PLUS_FEATURE_NAMES = (
    # physical, identical to v1.0 and v2.0
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
    # design: the v2.0 absolute statistics
    "cell_count_log",
    "wire_count_log",
    "wire_bit_count_log",
    "public_wire_ratio",
    "cell_type_diversity",
    "sequential_ratio",
    "combinational_ratio",
    "memory_bit_count_log",
    # design: reference-relative features restored in v2.1
    "netlist_delta_ratio",
    "simulation_failure_ratio",
    # supply chain, identical to v1.0 and v2.0
    "supplier_risk",
    "country_risk",
    "custody_gap_ratio",
    "certificate_risk",
    "sbom_mismatch_ratio",
    "threat_intel_score",
    "puf_instability",
    "opentitan_risk",
)

FEATURE_SCHEMAS = {
    FEATURE_SCHEMA_VERSION: FEATURE_NAMES,
    CANDIDATE_FEATURE_SCHEMA_VERSION: CANDIDATE_FEATURE_NAMES,
    CANDIDATE_PLUS_FEATURE_SCHEMA_VERSION: CANDIDATE_PLUS_FEATURE_NAMES,
}
