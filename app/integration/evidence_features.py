"""Purpose: Derive v2.1 relative design features from verified hardware stage results.

Directory: app/integration
Dependencies: standard library only, so the derivations are unit-testable in isolation
Connection: consumed by app/integration/adapters.py::build_ai_evidence

Every function returns an explicit absence rather than a default. A missing feature must
stay missing so that the hardware-to-AI contract check fails closed; substituting 0.0 for
an unmeasured feature would present the model with a constant column and silently degrade
the decision without any test detecting it.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# v1.0 design features the hardware pipeline cannot supply. Both are obtainable by
# established methods and neither is implemented here:
#   unused_logic_ratio  second synthesis pass, opt_clean -purge cell-count delta
#   rare_net_ratio      static signal-probability and controllability analysis
# This is a scope decision, not a claim of infeasibility.
UNIMPLEMENTED_V1_FEATURES = (
    "yosys.unused_logic_ratio",
    "yosys.rare_net_count",
)

# Feature names required by each schema version that must be derived here rather than
# read straight from a stage result.
RELATIVE_FEATURES_BY_SCHEMA: dict[str, tuple[str, ...]] = {
    "1.0": (
        "yosys.gate_count",
        "yosys.unused_logic_ratio",
        "yosys.rare_net_count",
        "yosys.netlist_delta_ratio",
    ),
    "2.0": (),
    "2.1": (
        "yosys.netlist_delta_ratio",
        "verilator.failed_assertions",
    ),
}

ASSERTION_FAILURE_REASON = "SIMULATION_ASSERTION_FAILURE"

# Evidence classes contributing to the evidence_quality composite, with declared weights.
# The score is the weighted fraction of evidence classes independently verified. It is an
# auditable completeness measure, not a confidence estimate, and it is documented as such
# because calibration.confidence_score() weights it at 0.20 of the final confidence.
EVIDENCE_QUALITY_WEIGHTS: dict[str, float] = {
    "yosys_passed": 0.15,
    "verilator_passed": 0.15,
    "chipwhisperer_passed": 0.15,
    "opentitan_verified": 0.15,
    "puf_verified": 0.20,
    "digital_twin_verified": 0.10,
    "structural_baseline_applied": 0.05,
    "physical_capture": 0.05,
}


class EvidenceDerivationError(ValueError):
    """Raised when a stage result is structurally invalid rather than merely absent."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _passed(stage: Any) -> bool:
    return bool(_mapping(stage).get("passed", False))


def netlist_delta_ratio(yosys_stage: Any) -> float | None:
    """Return the reference-relative netlist delta ratio, or None if not measured.

    Produced by YosysAdapter.analyse_against_reference(), which synthesises the candidate
    and a known-good reference and normalises the absolute cell delta by the reference
    cell count. A ratio of 0.0 means structurally identical to the reference; it is a
    measured value and must not be confused with an absent one.
    """
    stage = _mapping(yosys_stage)

    for container in (
        stage.get("structural_delta"),
        stage.get("structural_delta_report"),
        stage,
    ):
        report = _mapping(container)
        if "netlist_delta_ratio" not in report:
            continue

        try:
            value = float(report["netlist_delta_ratio"])
        except (TypeError, ValueError) as exc:
            raise EvidenceDerivationError(
                "netlist_delta_ratio is present but not numeric"
            ) from exc

        if not math.isfinite(value) or value < 0.0:
            raise EvidenceDerivationError(
                f"netlist_delta_ratio must be finite and non-negative, got {value!r}"
            )

        return min(1.0, value)

    return None


def failed_assertions(verilator_stage: Any) -> tuple[int, bool] | None:
    """Return (count, is_exact) for failed assertions, or None if undeterminable.

    VerilatorResult carries no failed-assertion count. parse_output() signals failure by
    appending SIMULATION_ASSERTION_FAILURE to reasons. Where an explicit count is present
    it is used and reported as exact. Where only the reason is present, 1 is returned as
    an explicit LOWER BOUND with is_exact False, and the caller must record that. Where
    the stage passed with no failure reason, 0 is exact.
    """
    stage = _mapping(verilator_stage)

    if not stage:
        return None

    if "failed_assertions" in stage:
        try:
            count = int(stage["failed_assertions"])
        except (TypeError, ValueError) as exc:
            raise EvidenceDerivationError(
                "failed_assertions is present but not an integer"
            ) from exc
        if count < 0:
            raise EvidenceDerivationError(
                f"failed_assertions must be non-negative, got {count}"
            )
        return count, True

    reasons = stage.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        return None

    upper = {str(reason).upper() for reason in reasons}

    if ASSERTION_FAILURE_REASON in upper:
        return 1, False

    if _passed(stage):
        return 0, True

    return None


def simulation_failure_ratio(
    verilator_stage: Any,
) -> tuple[float, bool] | None:
    """Return (ratio, is_exact) of failed to total assertions, or None if undeterminable."""
    stage = _mapping(verilator_stage)
    derived = failed_assertions(stage)

    if derived is None:
        return None

    count, exact = derived

    try:
        total = int(stage.get("assertions", 0))
    except (TypeError, ValueError) as exc:
        raise EvidenceDerivationError(
            "Verilator assertion count is not an integer"
        ) from exc

    if total <= 0:
        return None

    return min(1.0, count / total), exact


def evidence_quality(
    *,
    stages: Any,
    puf_verified: bool,
    physical_capture: bool,
    structural_baseline_applied: bool,
) -> float:
    """Return the weighted fraction of evidence classes independently verified, in [0, 1].

    Documented as a completeness measure. calibration.confidence_score() weights it at
    0.20, so a pinned value directly caps achievable confidence.
    """
    resolved = _mapping(stages)

    observed: dict[str, bool] = {
        "yosys_passed": _passed(resolved.get("yosys")),
        "verilator_passed": _passed(resolved.get("verilator")),
        "chipwhisperer_passed": _passed(resolved.get("chipwhisperer")),
        "opentitan_verified": _passed(resolved.get("opentitan")),
        "puf_verified": bool(puf_verified),
        "digital_twin_verified": _passed(resolved.get("digital_twin")),
        "structural_baseline_applied": bool(structural_baseline_applied),
        "physical_capture": bool(physical_capture),
    }

    total = sum(EVIDENCE_QUALITY_WEIGHTS.values())

    if total <= 0.0:
        raise EvidenceDerivationError("evidence quality weights sum to zero")

    achieved = sum(
        weight
        for name, weight in EVIDENCE_QUALITY_WEIGHTS.items()
        if observed.get(name, False)
    )

    return min(1.0, max(0.0, achieved / total))


def missing_model_features(
    *,
    schema_version: str,
    netlist_delta: float | None,
    simulation_failure: tuple[float, bool] | None,
    puf_verified: bool,
) -> list[str]:
    """Return the model features the hardware pipeline could not supply for this schema.

    Replaces the unconditional list in build_ai_evidence, which was hardwired non-empty
    and therefore made hardware_ai_contract_complete permanently False. Under schema 1.0
    it still fails closed, correctly, because two of the four v1.0 design features are
    not implemented.
    """
    required = RELATIVE_FEATURES_BY_SCHEMA.get(schema_version)

    if required is None:
        raise EvidenceDerivationError(
            f"unknown feature schema version: {schema_version!r}"
        )

    missing: list[str] = []

    for feature in required:
        if feature in UNIMPLEMENTED_V1_FEATURES:
            missing.append(feature)
        elif feature == "yosys.gate_count":
            missing.append(feature)
        elif feature == "yosys.netlist_delta_ratio" and netlist_delta is None:
            missing.append(feature)
        elif feature == "verilator.failed_assertions" and simulation_failure is None:
            missing.append(feature)

    if not puf_verified:
        missing.append("puf.verified_authentication")

    return missing
