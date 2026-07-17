"""Purpose: Accept terminal-originated JSON chip scans without authentication.
Directory: app/api/routes.
Dependencies: Flask, JSON schema validation, EventStore, SocketPublisher.
Connection: Creates the first immutable scan event and broadcasts it to read-only clients.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid4, uuid5

from flask import Blueprint, current_app, g, request

from app.api.response import success
from app.constants import IDEMPOTENCY_HEADER, EventType, ScanStatus
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.extensions import audit_writer, event_store
from app.security.schema_validation import validate_payload

bp = Blueprint("scan_submission", __name__)


@bp.post("/scans")
def submit_scan():
    if not current_app.config["PLATFORM_CONFIG"]["api"].get("scan_submission_enabled", True):
        raise ConflictError("Scan submission is disabled")
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    payload = request.get_json(silent=False)
    validate_payload("scan_submission", payload)

    chip_id = str(payload["chip_id"])
    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    supplied_scan_id = payload.get("scan_id")
    if supplied_scan_id:
        scan_id = str(supplied_scan_id)
    elif idempotency_key:
        scan_id = str(uuid5(NAMESPACE_URL, f"semisecure:{chip_id}:{idempotency_key}"))
    else:
        scan_id = str(uuid4())

    try:
        existing = event_store().snapshot(scan_id)
    except NotFoundError:
        existing = None
    if existing is not None:
        return success(existing, status=200, meta={"idempotent_replay": True})

    event = event_store().append(
        scan_id=scan_id,
        chip_id=chip_id,
        event_type=EventType.SCAN_ACCEPTED,
        pipeline_stage="INGESTION",
        correlation_id=g.correlation_id,
        source_component="flask-api",
        component_version=current_app.config["PLATFORM_CONFIG"]["application"]["version"],
        payload={
            "status": ScanStatus.RECEIVED,
            "chip_file": payload.get("chip_file"),
            "source": payload.get("source", {}),
            "evidence": payload["evidence"],
            "metadata": payload.get("metadata", {}),
        },
        reject_existing_scan=True,
    )
    audit_writer().write(
        "scan.accepted",
        g.correlation_id,
        {"scan_id": scan_id, "chip_id": chip_id, "event_id": event.event_id},
    )
    publisher = current_app.extensions.get("semisecure.socket_publisher")
    if publisher is not None:
        publisher.publish_record(event)
    return success(event.to_dict(), status=202)

