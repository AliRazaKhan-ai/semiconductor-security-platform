"""Read and enrich immutable scan projections for the dashboard."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, request

from app.api.response import success
from app.exceptions import ValidationError
from app.extensions import event_store


bp = Blueprint("scan_queries", __name__)


def _bounded_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = request.args.get(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(
            f"Query parameter {name!r} must be an integer"
        ) from exc

    if value < minimum or value > maximum:
        raise ValidationError(
            f"Query parameter {name!r} is outside the allowed range",
            {
                "minimum": minimum,
                "maximum": maximum,
            },
        )

    return value


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value

    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result


def _stage_value(
    stage: dict[str, Any],
    key: str,
) -> Any:
    return _first(
        stage.get(key),
        (
            stage.get("result", {}).get(key)
            if isinstance(stage.get("result"), dict)
            else None
        ),
        (
            stage.get("details", {}).get(key)
            if isinstance(stage.get("details"), dict)
            else None
        ),
    )


def _metadata_from_run(
    run: dict[str, Any],
) -> dict[str, Any]:
    """Recover immutable chip metadata from the run or source JSON."""
    scan = run.get("scan")

    if isinstance(scan, dict):
        candidates = [scan.get("metadata")]

        payload = scan.get("payload")
        if isinstance(payload, dict):
            candidates.extend([
                payload.get("metadata"),
                payload,
            ])

        latest_payload = scan.get("latest_payload")
        if isinstance(latest_payload, dict):
            candidates.extend([
                latest_payload.get("metadata"),
                latest_payload,
            ])

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if any(
                key in candidate
                for key in (
                    "manufacturing",
                    "supplier",
                    "supply_chain",
                    "hardware_security",
                    "compliance",
                )
            ):
                return candidate

    source_file = run.get("source_file")
    if isinstance(source_file, str) and source_file.strip():
        import json
        from pathlib import Path

        path = Path(source_file).expanduser()
        if path.is_file():
            try:
                simulation = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                simulation = None

            if isinstance(simulation, dict):
                return {
                    "manufacturing": simulation.get("manufacturing", {}),
                    "supplier": simulation.get("supplier", {}),
                    "supply_chain": simulation.get("supply_chain", {}),
                    "hardware_security": simulation.get("hardware_security", {}),
                    "compliance": simulation.get("compliance", {}),
                    "failure_reason": simulation.get("failure_reason"),
                    "expected_results": simulation.get("expected_results", {}),
                }

    return {}


def _load_run(scan_id: str) -> dict[str, Any] | None:
    service = current_app.extensions.get(
        "semisecure.integrated_pipeline"
    )

    if service is None:
        return None

    getter = getattr(service, "get_run", None)

    if not callable(getter):
        return None

    try:
        run = getter(scan_id)
    except (FileNotFoundError, OSError, ValueError):
        return None

    return run if isinstance(run, dict) else None


def _enrich_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    scan_id = str(snapshot.get("scan_id") or "")

    if not scan_id:
        return snapshot

    run = _load_run(scan_id)

    if not run:
        return snapshot

    compliance = (
        run.get("compliance")
        if isinstance(run.get("compliance"), dict)
        else {}
    )

    decision = (
        compliance.get("decision")
        if isinstance(compliance.get("decision"), dict)
        else {}
    )

    ai = (
        run.get("ai")
        if isinstance(run.get("ai"), dict)
        else {}
    )

    compliance_ai = (
        decision.get("ai")
        if isinstance(decision.get("ai"), dict)
        else {}
    )

    stages = (
        run.get("stages")
        if isinstance(run.get("stages"), list)
        else []
    )

    stage_risks = [
        value
        for stage in stages
        if isinstance(stage, dict)
        for value in [_number(_stage_value(stage, "risk_score"))]
        if value is not None
    ]

    stage_confidences = [
        value
        for stage in stages
        if isinstance(stage, dict)
        for value in [_number(_stage_value(stage, "confidence"))]
        if value is not None
    ]

    risk_score = _first(
        _number(decision.get("risk_score")),
        _number(ai.get("risk_score")),
        max(stage_risks) if stage_risks else None,
    )

    confidence = _first(
        _number(decision.get("confidence")),
        _number(ai.get("confidence")),
        _number(compliance_ai.get("confidence_score")),
        stage_confidences[-1] if stage_confidences else None,
    )

    supplier_risk_record = _first(
        compliance.get("supplier_risk"),
        decision.get("supplier_risk"),
    )

    supplier_risk = (
        _number(supplier_risk_record.get("risk_score"))
        if isinstance(supplier_risk_record, dict)
        else _number(supplier_risk_record)
    )

    blockchain = _first(
        run.get("blockchain"),
        compliance.get("blockchain"),
    )

    if not isinstance(blockchain, dict):
        blockchain = {}

    fabric = (
        blockchain.get("fabric")
        if isinstance(blockchain.get("fabric"), dict)
        else {}
    )

    ethereum = (
        blockchain.get("ethereum")
        if isinstance(blockchain.get("ethereum"), dict)
        else {}
    )

    metadata = _metadata_from_run(run)

    tensorflow = _first(
        ai.get("tensorflow"),
        ai.get("confidence"),
        compliance_ai.get("confidence_score"),
    )

    if isinstance(tensorflow, dict):
        tensorflow = _first(
            tensorflow.get("confidence"),
            tensorflow.get("score"),
            tensorflow.get("probability"),
        )

    pytorch = _first(
        ai.get("pytorch"),
        ai.get("risk_score"),
        compliance_ai.get("risk_score"),
    )

    if isinstance(pytorch, dict):
        pytorch = _first(
            pytorch.get("anomaly_score"),
            pytorch.get("score"),
            pytorch.get("probability"),
        )

    enriched = {
        **snapshot,
        "run_id": run.get("run_id"),
        "scenario": run.get("scenario"),
        "status": run.get("status") or snapshot.get("status"),
        "active_stage": run.get("active_stage"),
        "stopped_stage": run.get("stopped_stage"),
        "current_stage": (
            run.get("stopped_stage")
            or run.get("active_stage")
            or snapshot.get("current_stage")
        ),
        "updated_at": (
            run.get("updated_at_utc")
            or run.get("completed_at_utc")
            or snapshot.get("updated_at")
        ),
        "deployment_decision": run.get(
            "deployment_decision"
        ),
        "quarantined": bool(run.get("quarantined")),
        "risk_score": risk_score,
        "overall_risk": risk_score,
        "confidence": confidence,
        "supplier_risk": supplier_risk,
        "tensorflow_score": tensorflow,
        "pytorch_score": pytorch,
        "ai_classification": _first(
            ai.get("classification"),
            compliance_ai.get("classification"),
            run.get("scenario"),
        ),
        "ai": ai,
        "hardware": run.get("hardware"),
        "hardware_security": metadata.get(
            "hardware_security",
            {},
        ),
        "manufacturing": metadata.get(
            "manufacturing",
            {},
        ),
        "supplier": metadata.get(
            "supplier",
            {},
        ),
        "supply_chain": metadata.get(
            "supply_chain",
            {},
        ),
        "compliance": compliance or None,
        "blockchain": blockchain or None,
        "fabric_committed": bool(
            fabric.get("committed")
        ),
        "fabric_validation": fabric.get(
            "validation_code"
        ),
        "fabric_tx": fabric.get(
            "transaction_id"
        ),
        "ethereum_confirmed": bool(
            ethereum.get("confirmed")
        ),
        "ethereum_tx": ethereum.get(
            "transaction_hash"
        ),
        "stages": stages,
    }

    return enriched


@bp.get("/scans/latest")
def latest_scans():
    limit = _bounded_int(
        "limit",
        50,
        1,
        500,
    )

    raw_items = event_store().latest(limit)

    items = [
        _enrich_snapshot(dict(item))
        for item in raw_items
        if isinstance(item, dict)
    ]

    return success(
        items,
        meta={
            "count": len(items),
            "limit": limit,
            "enriched": True,
        },
    )


@bp.get("/scans/<scan_id>")
def scan_summary(scan_id: str):
    snapshot = event_store().snapshot(scan_id)

    return success(
        _enrich_snapshot(dict(snapshot))
    )


@bp.get("/scans/<scan_id>/events")
def scan_events(scan_id: str):
    after_sequence = _bounded_int(
        "after_sequence",
        0,
        0,
        10_000_000,
    )

    limit = _bounded_int(
        "limit",
        500,
        1,
        5000,
    )

    events = event_store().events(
        scan_id,
        after_sequence=after_sequence,
        limit=limit,
    )

    return success(
        [
            event.to_dict()
            for event in events
        ],
        meta={
            "count": len(events),
            "after_sequence": after_sequence,
            "limit": limit,
        },
    )
