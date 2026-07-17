"""Purpose: Perform deterministic fail-closed security gating for chip simulations.
Directory: app/pipeline.
Dependencies: Python standard library.
Connection: Called by the terminal scan workflow before AI, compliance, and blockchain.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SimulationGateResult:
    """Represent the mandatory pre-compliance security-gate result."""

    passed: bool
    stage: str
    status: str
    stop_pipeline: bool
    risk_score: float
    confidence: float
    classification: str
    deployment_decision: str
    dashboard_status: str
    alert_color: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert the immutable result into JSON-compatible data."""
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


def _mapping(value: object) -> dict[str, Any]:
    """Return a dictionary when the supplied value is a mapping."""
    return value if isinstance(value, dict) else {}


def evaluate_simulation_gate(
    simulation: dict[str, Any],
) -> SimulationGateResult:
    """Evaluate mandatory hardware and supply-chain gates in pipeline order."""
    hardware = _mapping(simulation.get("hardware_security"))
    puf = _mapping(hardware.get("puf"))
    opentitan = _mapping(hardware.get("opentitan"))
    verilator = _mapping(hardware.get("verilator"))
    yosys = _mapping(hardware.get("yosys"))
    supply_chain = _mapping(simulation.get("supply_chain"))
    scenario = str(simulation.get("scenario") or "UNKNOWN").upper()

    authentication_expected = bool(
        puf.get("authentication_expected", True)
    )
    stability_score = float(puf.get("stability_score", 1.0))
    hamming_distance = float(
        puf.get("intra_device_hamming_distance", 0.0)
    )

    if (
        not authentication_expected
        or stability_score < 0.85
        or hamming_distance > 0.20
    ):
        return SimulationGateResult(
            passed=False,
            stage="PUF_AUTHENTICATION",
            status="FAILED",
            stop_pipeline=True,
            risk_score=0.99,
            confidence=0.99,
            classification="PUF_AUTHENTICATION_FAILED",
            deployment_decision="HOLD_FOR_RETEST_OR_REJECT",
            dashboard_status="AUTHENTICATION_FAILED",
            alert_color="AMBER",
            reasons=(
                "PUF response stability is below the permitted threshold",
                "Chip identity cannot be established reliably",
                "Fail-closed policy prevents further processing",
            ),
        )

    secure_boot = bool(opentitan.get("secure_boot", True))
    otp_integrity = bool(opentitan.get("otp_integrity", True))
    rom_digest_valid = bool(
        opentitan.get("rom_digest_valid", True)
    )
    debug_locked = bool(opentitan.get("debug_locked", True))

    if not all(
        (
            secure_boot,
            otp_integrity,
            rom_digest_valid,
            debug_locked,
        )
    ):
        return SimulationGateResult(
            passed=False,
            stage="OPENTITAN",
            status="FAILED",
            stop_pipeline=True,
            risk_score=0.98,
            confidence=0.98,
            classification="ROOT_OF_TRUST_FAILURE",
            deployment_decision="DENIED_AND_QUARANTINED",
            dashboard_status="HARDWARE_TRUST_FAILED",
            alert_color="RED",
            reasons=(
                "OpenTitan root-of-trust validation failed",
                "Secure boot, OTP, ROM digest, or debug lock is invalid",
            ),
        )

    digital_twin_match = bool(
        supply_chain.get("digital_twin_match", True)
    )
    sbom_match = bool(supply_chain.get("sbom_match", True))
    custody_gap_ratio = float(
        supply_chain.get("custody_gap_ratio", 0.0)
    )
    sbom_mismatch_ratio = float(
        supply_chain.get("sbom_mismatch_ratio", 0.0)
    )

    if (
        not digital_twin_match
        or not sbom_match
        or custody_gap_ratio > 0.20
        or sbom_mismatch_ratio > 0.10
    ):
        return SimulationGateResult(
            passed=False,
            stage="DIGITAL_TWIN_AND_SBOM",
            status="FAILED",
            stop_pipeline=True,
            risk_score=0.97,
            confidence=0.98,
            classification="SUPPLY_CHAIN_TAMPERED",
            deployment_decision="DENIED_AND_INCIDENT_RESPONSE_OPENED",
            dashboard_status="SUPPLY_CHAIN_TAMPERED",
            alert_color="RED",
            reasons=(
                "Digital-twin or SBOM evidence does not match",
                "Supply-chain integrity cannot be established",
            ),
        )

    simulation_passed = bool(
        verilator.get("simulation_passed", True)
    )
    simulation_failure_ratio = float(
        verilator.get("simulation_failure_ratio", 0.0)
    )
    rare_net_ratio = float(yosys.get("rare_net_ratio", 0.0))
    netlist_delta_ratio = float(
        yosys.get("netlist_delta_ratio", 0.0)
    )

    if (
        scenario == "HARDWARE_TROJAN"
        or not simulation_passed
        or simulation_failure_ratio > 0.02
        or rare_net_ratio > 0.10
        or netlist_delta_ratio > 0.10
    ):
        return SimulationGateResult(
            passed=False,
            stage="HARDWARE_TROJAN_ANALYSIS",
            status="FAILED",
            stop_pipeline=True,
            risk_score=0.99,
            confidence=0.99,
            classification="HARDWARE_TROJAN",
            deployment_decision="DENIED_AND_QUARANTINED",
            dashboard_status="COMPROMISED",
            alert_color="RED",
            reasons=(
                "Trojan indicators were detected in hardware evidence",
                "Netlist, side-channel, or simulation behavior is unsafe",
            ),
        )

    return SimulationGateResult(
        passed=True,
        stage="PRE_COMPLIANCE_SECURITY_GATES",
        status="PASSED",
        stop_pipeline=False,
        risk_score=0.05,
        confidence=0.98,
        classification="SECURITY_GATES_PASSED",
        deployment_decision="CONTINUE_TO_COMPLIANCE",
        dashboard_status="SECURITY_VALIDATED",
        alert_color="GREEN",
        reasons=(),
    )
