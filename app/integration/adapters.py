"""Exact adapters for the registered hardware and AI pipeline services."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from app.hardware.chipwhisperer.capture import load_trace_evidence
from app.hardware.common import HardwareIntegrationError


class AdapterError(RuntimeError):
    """Raised when a registered service cannot be invoked safely."""


HARDWARE_MANIFEST_KEYS = (
    "opentitan_evidence",
    "side_channel_trace",
    "side_channel_reference",
    "ai_em_trace",
    "ai_timing_trace",
    "rtl_file",
    "testbench_file",
    "top_module",
    "sbom_artifacts",
    "puf_identity_hash",
    "twin_id",
)


def serialise_result(value: Any) -> dict[str, Any]:
    """Convert service result objects into JSON-compatible dictionaries."""
    if isinstance(value, dict):
        return value

    to_dict = getattr(value, "to_dict", None)

    if callable(to_dict):
        result = to_dict()

        if not isinstance(result, dict):
            raise AdapterError(
                f"{type(value).__name__}.to_dict() did not return a dictionary"
            )

        return result

    if is_dataclass(value):
        result = asdict(value)

        if isinstance(result, dict):
            return result

    attributes: dict[str, Any] = {}

    for name in (
        "passed",
        "status",
        "classification",
        "results",
        "failed_stage",
        "decision",
        "risk_score",
        "confidence",
    ):
        if hasattr(value, name):
            attributes[name] = getattr(value, name)

    if attributes:
        return attributes

    raise AdapterError(
        f"Unsupported service result type: {type(value).__name__}"
    )


def _resolve_path(
    root: Path,
    raw_value: object,
    *,
    field_name: str,
) -> str:
    value = str(raw_value or "").strip()

    if not value:
        raise AdapterError(
            f"Hardware manifest field {field_name!r} is empty"
        )

    path = Path(value).expanduser()

    if not path.is_absolute():
        path = root / path

    path = path.resolve()

    if not path.exists():
        raise AdapterError(
            f"Hardware evidence does not exist for {field_name}: {path}"
        )

    return str(path)


def build_hardware_manifest(
    *,
    project_root: Path,
    simulation: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract and validate the real hardware evidence manifest."""
    candidates = (
        simulation.get("hardware_manifest"),
        simulation.get("manifest"),
        (
            simulation.get("hardware_security", {}).get("manifest")
            if isinstance(simulation.get("hardware_security"), dict)
            else None
        ),
    )

    manifest = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, dict)
        ),
        None,
    )

    if manifest is None:
        raise AdapterError(
            "The chip simulation has no real hardware manifest. "
            "Add a hardware_manifest object containing OpenTitan evidence, "
            "side-channel power trace/reference, AI EM trace, AI timing trace, "
            "RTL, testbench, top module, SBOM artifacts, PUF identity hash, "
            "and twin ID."
        )

    missing = [
        key
        for key in HARDWARE_MANIFEST_KEYS
        if key not in manifest
    ]

    if missing:
        raise AdapterError(
            "Hardware manifest is missing required fields: "
            + ", ".join(missing)
        )

    normalised = dict(manifest)

    for key in (
        "opentitan_evidence",
        "side_channel_trace",
        "side_channel_reference",
        "ai_em_trace",
        "ai_timing_trace",
        "rtl_file",
        "testbench_file",
    ):
        normalised[key] = _resolve_path(
            project_root,
            manifest[key],
            field_name=key,
        )

    artifacts = manifest["sbom_artifacts"]

    if not isinstance(artifacts, list) or not artifacts:
        raise AdapterError(
            "hardware_manifest.sbom_artifacts must be a non-empty list"
        )

    normalised["sbom_artifacts"] = [
        _resolve_path(
            project_root,
            value,
            field_name=f"sbom_artifacts[{index}]",
        )
        for index, value in enumerate(artifacts)
    ]

    normalised["top_module"] = str(
        manifest["top_module"]
    ).strip()
    normalised["puf_identity_hash"] = str(
        manifest["puf_identity_hash"]
    ).strip()
    normalised["twin_id"] = str(
        manifest["twin_id"]
    ).strip()

    for key in (
        "top_module",
        "puf_identity_hash",
        "twin_id",
    ):
        if not normalised[key]:
            raise AdapterError(
                f"Hardware manifest field {key!r} is empty"
            )

    return normalised


def run_hardware_pipeline(
    *,
    service: Any,
    project_root: Path,
    simulation: Mapping[str, Any],
    scan_id: str,
    chip_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Invoke HardwareSecurityPipeline.run using its exact contract."""
    if service is None:
        raise AdapterError(
            "HardwareSecurityPipeline is not registered"
        )

    run = getattr(service, "run", None)

    if not callable(run):
        raise AdapterError(
            "Registered hardware service has no callable run() method"
        )

    manifest = build_hardware_manifest(
        project_root=project_root,
        simulation=simulation,
    )

    result_object = run(
        scan_id=scan_id,
        chip_id=chip_id,
        correlation_id=correlation_id,
        manifest=manifest,
    )

    result = serialise_result(result_object)
    passed = bool(result.get("passed", False))
    status = str(
        result.get("status")
        or result.get("classification")
        or (
            "HARDWARE_VALIDATED"
            if passed
            else "QUARANTINED"
        )
    )

    return {
        "passed": passed,
        "classification": status,
        "risk_score": 0.05 if passed else 1.0,
        "confidence": 1.0,
        "reasons": (
            []
            if passed
            else [
                f"Hardware pipeline failed at "
                f"{result.get('failed_stage') or 'unknown stage'}"
            ]
        ),
        "deployment_decision": (
            "CONTINUE"
            if passed
            else "DENIED_AND_QUARANTINED"
        ),
        "manifest": manifest,
        "service_output": result,
    }


def _required_mapping(
    value: object,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterError(
            f"{name} must be a dictionary"
        )

    return value


def _validated_hardware_stages(
    hardware_result: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not bool(
        hardware_result.get(
            "passed",
            False,
        )
    ):
        raise AdapterError(
            "AI analysis requires a passed hardware pipeline result"
        )

    service_output = _required_mapping(
        hardware_result.get(
            "service_output"
        ),
        name="hardware service output",
    )

    stages = _required_mapping(
        service_output.get(
            "results"
        ),
        name="hardware stage results",
    )

    required = (
        "opentitan",
        "chipwhisperer",
        "yosys",
        "verilator",
        "sbom",
        "digital_twin",
    )

    for stage_name in required:
        stage = _required_mapping(
            stages.get(
                stage_name
            ),
            name=f"hardware stage {stage_name}",
        )

        if not bool(
            stage.get(
                "passed",
                False,
            )
        ):
            raise AdapterError(
                f"hardware stage {stage_name} is not verified"
            )

    return stages


def _load_ai_trace(
    path_value: object,
    *,
    role: str,
):
    raw_path = str(
        path_value
        or ""
    ).strip()

    if not raw_path:
        raise AdapterError(
            f"{role} path is missing"
        )

    try:
        evidence = load_trace_evidence(
            Path(raw_path)
        )
    except HardwareIntegrationError as exc:
        raise AdapterError(
            f"{role} could not be validated: {exc}"
        ) from exc

    if (
        evidence.source_type
        == "PHYSICAL_CAPTURE"
    ):
        raise AdapterError(
            f"{role} claims PHYSICAL_CAPTURE but physical "
            "capture verification is not implemented"
        )

    return evidence


def build_ai_evidence(
    *,
    simulation: Mapping[str, Any],
    puf_result: Mapping[str, Any],
    hardware_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build strict AI evidence from explicit and verified preceding evidence."""

    if isinstance(
        simulation.get(
            "ai_evidence"
        ),
        dict,
    ):
        raise AdapterError(
            "Strict AI integration does not accept simulation ai_evidence overrides"
        )

    stages = _validated_hardware_stages(
        hardware_result
    )

    manifest = _required_mapping(
        hardware_result.get(
            "manifest"
        ),
        name="hardware manifest",
    )

    power = _load_ai_trace(
        manifest.get(
            "side_channel_trace"
        ),
        role="AI power trace",
    )

    em = _load_ai_trace(
        manifest.get(
            "ai_em_trace"
        ),
        role="AI EM trace",
    )

    timing = _load_ai_trace(
        manifest.get(
            "ai_timing_trace"
        ),
        role="AI timing trace",
    )

    chipwhisperer = _required_mapping(
        stages.get(
            "chipwhisperer"
        ),
        name="ChipWhisperer result",
    )

    candidate_digest = str(
        chipwhisperer.get(
            "candidate_file_digest"
        )
        or ""
    )

    if (
        not candidate_digest
        or candidate_digest
        != power.file_digest
    ):
        raise AdapterError(
            "AI power trace is not bound to the verified "
            "ChipWhisperer candidate file"
        )

    hardware_source = str(
        chipwhisperer.get(
            "candidate_source_type"
        )
        or ""
    ).upper()

    if (
        hardware_source
        != power.source_type
    ):
        raise AdapterError(
            "AI power-trace provenance does not match "
            "the ChipWhisperer result"
        )

    yosys = _required_mapping(
        stages.get(
            "yosys"
        ),
        name="Yosys result",
    )

    yosys_metrics = _required_mapping(
        yosys.get(
            "metrics"
        ),
        name="Yosys metrics",
    )

    cell_types = _required_mapping(
        yosys_metrics.get(
            "cell_types"
        ),
        name="Yosys cell types",
    )

    cells = int(
        yosys_metrics.get(
            "cells",
            0,
        )
    )

    wires = int(
        yosys_metrics.get(
            "wires",
            0,
        )
    )

    wire_bits = int(
        yosys_metrics.get(
            "wire_bits",
            0,
        )
    )

    public_wires = int(
        yosys_metrics.get(
            "public_wires",
            0,
        )
    )

    memory_bits = int(
        yosys_metrics.get(
            "memory_bits",
            0,
        )
    )

    if cells <= 0:
        raise AdapterError(
            "Yosys metrics contain no synthesized cells"
        )

    if min(
        wires,
        wire_bits,
        public_wires,
        memory_bits,
    ) < 0:
        raise AdapterError(
            "Yosys metrics contain negative structural counts"
        )

    if public_wires > wires:
        raise AdapterError(
            "Yosys public-wire count exceeds total wires"
        )

    sequential_cells = sum(
        int(count)
        for name, count
        in cell_types.items()
        if (
            "DFF"
            in str(name).upper()
            or "LATCH"
            in str(name).upper()
        )
    )

    combinational_cells = max(
        0,
        cells
        - sequential_cells,
    )

    verilator = _required_mapping(
        stages.get(
            "verilator"
        ),
        name="Verilator result",
    )

    assertion_count = int(
        verilator.get(
            "assertions",
            0,
        )
    )

    if assertion_count <= 0:
        raise AdapterError(
            "Verilator result contains no verified assertions"
        )

    opentitan = _required_mapping(
        stages.get(
            "opentitan"
        ),
        name="OpenTitan result",
    )

    digital_twin = _required_mapping(
        stages.get(
            "digital_twin"
        ),
        name="digital-twin result",
    )

    puf_details = _required_mapping(
        puf_result.get(
            "details"
        ),
        name="PUF result details",
    )

    if (
        "stability_score"
        not in puf_details
    ):
        raise AdapterError(
            "PUF result contains no stability_score"
        )

    stability_score = float(
        puf_details[
            "stability_score"
        ]
    )

    if (
        not math.isfinite(
            stability_score
        )
        or stability_score < 0.0
        or stability_score > 1.0
    ):
        raise AdapterError(
            "PUF stability_score must be between 0 and 1"
        )

    puf_source = str(
        puf_result.get(
            "verification_source"
        )
        or "UNSPECIFIED"
    ).upper()

    verified_puf = bool(
        puf_result.get(
            "passed",
            False,
        )
    ) and (
        puf_source
        == "VERIFIED_PUF_STAGE"
    )

    supply_chain = simulation.get(
        "supply_chain",
        {},
    )

    if not isinstance(
        supply_chain,
        Mapping,
    ):
        supply_chain = {}

    missing_model_features = [
        "yosys.gate_count",
        "yosys.unused_logic_ratio",
        "yosys.rare_net_count",
        "yosys.netlist_delta_ratio",
    ]

    if not verified_puf:
        missing_model_features.append(
            "puf.verified_authentication"
        )

    return {
        "chip_id": simulation.get(
            "chip_id"
        ),
        "scenario": simulation.get(
            "scenario"
        ),
        "side_channel": {
            "power_trace": list(
                power.samples
            ),
            "em_trace": list(
                em.samples
            ),
            "timing_trace": list(
                timing.samples
            ),
        },
        "yosys": {
            "cell_count": cells,
            "wire_count": wires,
            "wire_bit_count": (
                wire_bits
            ),
            "public_wire_count": (
                public_wires
            ),
            "memory_bit_count": (
                memory_bits
            ),
            "cell_type_count": len(
                cell_types
            ),
            "sequential_cells": (
                sequential_cells
            ),
            "combinational_cells": (
                combinational_cells
            ),
        },
        "verilator": {
            "assertion_count": (
                assertion_count
            ),
            "failed_assertions": 0,
        },
        "puf": {
            "stability_score": (
                stability_score
            ),
            "verified_authentication": (
                verified_puf
            ),
            "evidence_class": (
                puf_source
            ),
        },
        "opentitan": {
            "verified": bool(
                opentitan.get(
                    "passed",
                    False,
                )
            ),
            "status": opentitan.get(
                "status"
            ),
            "evidence_digest": (
                opentitan.get(
                    "evidence_digest"
                )
            ),
            "lifecycle_state": (
                opentitan.get(
                    "lifecycle_state"
                )
            ),
            "firmware_digest": (
                opentitan.get(
                    "firmware_digest"
                )
            ),
            "monotonic_counter": (
                opentitan.get(
                    "monotonic_counter"
                )
            ),
        },
        "supply_chain": dict(
            supply_chain
        ),
        "hardware": dict(
            stages
        ),
        "evidence_quality": 0.0,
        "evidence_provenance": {
            "side_channel_analysis_mode": (
                chipwhisperer.get(
                    "analysis_mode"
                )
            ),
            "power_source_type": (
                power.source_type
            ),
            "power_file_sha256": (
                power.file_digest
            ),
            "em_source_type": (
                em.source_type
            ),
            "em_file_sha256": (
                em.file_digest
            ),
            "timing_source_type": (
                timing.source_type
            ),
            "timing_file_sha256": (
                timing.file_digest
            ),
            "physical_capture_verified": bool(
                chipwhisperer.get(
                    "physical_capture_verified",
                    False,
                )
            ),
            "digital_twin_verified": bool(
                digital_twin.get(
                    "passed",
                    False,
                )
            ),
            "puf_source": (
                puf_source
            ),
        },
        "hardware_ai_contract_complete": (
            not missing_model_features
        ),
        "hardware_ai_contract_missing": (
            missing_model_features
        ),
    }


def build_ai_controls(
    *,
    simulation: Mapping[str, Any],
    puf_result: Mapping[str, Any],
    hardware_result: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Build mandatory pre-AI controls from preceding stage outcomes."""

    if isinstance(
        simulation.get(
            "ai_controls"
        ),
        dict,
    ):
        raise AdapterError(
            "Strict AI integration does not accept simulation ai_controls overrides"
        )

    stages = _validated_hardware_stages(
        hardware_result
    )

    opentitan = _required_mapping(
        stages.get(
            "opentitan"
        ),
        name="OpenTitan result",
    )

    digital_twin = _required_mapping(
        stages.get(
            "digital_twin"
        ),
        name="digital-twin result",
    )

    puf_evidence = _required_mapping(
        evidence.get(
            "puf"
        ),
        name="PUF AI evidence",
    )

    compliance = simulation.get(
        "compliance",
        {},
    )

    if not isinstance(
        compliance,
        Mapping,
    ):
        compliance = {}

    return {
        "fail_closed": True,
        "puf_authenticated": bool(
            puf_evidence.get(
                "verified_authentication",
                False,
            )
        ),
        "puf_evidence_class": (
            puf_evidence.get(
                "evidence_class",
                "UNSPECIFIED",
            )
        ),
        "opentitan_verified": bool(
            opentitan.get(
                "passed",
                False,
            )
        ),
        "digital_twin_verified": bool(
            digital_twin.get(
                "passed",
                False,
            )
        ),
        "hardware_ai_contract_complete": bool(
            evidence.get(
                "hardware_ai_contract_complete",
                False,
            )
        ),
        "destination_country": (
            compliance.get(
                "destination_country",
                "",
            )
        ),
        "defense_related": bool(
            compliance.get(
                "defense_related",
                False,
            )
        ),
        "specially_designed_for_military": bool(
            compliance.get(
                "specially_designed_for_military",
                False,
            )
        ),
    }


def run_ai_pipeline(
    *,
    service: Any,
    simulation: Mapping[str, Any],
    puf_result: Mapping[str, Any],
    hardware_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Invoke AIPipelineService.analyze using its exact contract."""
    if service is None:
        raise AdapterError(
            "AIPipelineService is not registered"
        )

    analyze = getattr(service, "analyze", None)

    if not callable(analyze):
        raise AdapterError(
            "Registered AI service has no callable analyze() method"
        )

    evidence = build_ai_evidence(
        simulation=simulation,
        puf_result=puf_result,
        hardware_result=hardware_result,
    )

    controls = build_ai_controls(
        simulation=simulation,
        puf_result=puf_result,
        hardware_result=hardware_result,
        evidence=evidence,
    )

    if not bool(
        evidence.get(
            "hardware_ai_contract_complete",
            False,
        )
    ):
        missing = evidence.get(
            "hardware_ai_contract_missing",
            [],
        )

        raise AdapterError(
            "Hardware-to-AI feature contract is incomplete: "
            + ", ".join(
                str(item)
                for item in missing
            )
        )

    result = analyze(
        evidence=evidence,
        controls=controls,
    )

    if not isinstance(result, dict):
        raise AdapterError(
            "AI pipeline returned a non-dictionary result"
        )

    decision = result.get("decision")

    if not isinstance(decision, dict):
        raise AdapterError(
            "AI pipeline result contains no decision dictionary"
        )

    classification = str(
        decision.get("classification")
        or decision.get("label")
        or decision.get("decision")
        or ""
    ).upper()

    risk_score = float(
        decision.get("risk_score")
        or decision.get("score")
        or decision.get("probability")
        or 0.0
    )
    confidence = float(
        decision.get("confidence_score")
        or decision.get("confidence")
        or 0.0
    )

    if not classification:
        raise AdapterError(
            "AI decision contains no classification"
        )

    risk_score = max(0.0, min(1.0, risk_score))
    confidence = max(0.0, min(1.0, confidence))

    denied_labels = {
        "TROJAN",
        "TAMPERED",
        "MALICIOUS",
        "CRITICAL_ANOMALY",
        "DENIED",
        "QUARANTINED",
    }

    return {
        "passed": (
            classification not in denied_labels
            and risk_score < 0.85
        ),
        "classification": classification,
        "risk_score": risk_score,
        "confidence": confidence,
        "feature_vector": result.get("feature_vector"),
        "tensorflow": result.get("tensorflow"),
        "pytorch": result.get("pytorch"),
        "decision": decision,
        "evidence": evidence,
        "controls": controls,
        "service_output": result,
    }
