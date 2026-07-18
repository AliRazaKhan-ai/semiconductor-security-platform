"""Exact adapters for the registered hardware and AI pipeline services."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping


class AdapterError(RuntimeError):
    """Raised when a registered service cannot be invoked safely."""


HARDWARE_MANIFEST_KEYS = (
    "opentitan_evidence",
    "side_channel_trace",
    "side_channel_reference",
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
            "side-channel trace/reference, RTL, testbench, top module, SBOM "
            "artifacts, PUF identity hash, and twin ID."
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


def build_ai_evidence(
    *,
    simulation: Mapping[str, Any],
    hardware_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the evidence object consumed by AIPipelineService.analyze."""
    explicit = simulation.get("ai_evidence")

    if isinstance(explicit, dict):
        evidence = dict(explicit)
    else:
        evidence = {}

    hardware_output = hardware_result.get("service_output", {})
    hardware_stages = (
        hardware_output.get("results", {})
        if isinstance(hardware_output, dict)
        else {}
    )

    evidence.setdefault("chip_id", simulation.get("chip_id"))
    evidence.setdefault("scenario", simulation.get("scenario"))
    evidence.setdefault("hardware", hardware_stages)
    evidence.setdefault(
        "hardware_security",
        simulation.get("hardware_security", {}),
    )
    evidence.setdefault(
        "supply_chain",
        simulation.get("supply_chain", {}),
    )
    evidence.setdefault(
        "supplier",
        simulation.get("supplier", {}),
    )
    evidence.setdefault(
        "evidence_quality",
        float(simulation.get("evidence_quality", 1.0)),
    )

    return evidence


def build_ai_controls(
    simulation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build AI risk-engine controls from the chip transaction."""
    explicit = simulation.get("ai_controls")

    if isinstance(explicit, dict):
        return dict(explicit)

    compliance = simulation.get("compliance", {})

    if not isinstance(compliance, dict):
        compliance = {}

    return {
        "fail_closed": True,
        "destination_country": compliance.get(
            "destination_country",
            "",
        ),
        "defense_related": bool(
            compliance.get("defense_related", False)
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
        hardware_result=hardware_result,
    )
    controls = build_ai_controls(simulation)

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
