"""Read-only blockchain status, provenance queries, and terminal-triggered provenance commit."""
from __future__ import annotations

from flask import Blueprint, current_app, g, request

from app.api.response import success
from app.exceptions import NotFoundError, ValidationError

bp = Blueprint("blockchain_status", __name__)


def _service():
    service = current_app.extensions.get("semisecure.blockchain_service")
    if service is None:
        raise RuntimeError("blockchain service is unavailable")
    return service


@bp.get("/blockchain/status")
def blockchain_status():
    return success(_service().status())


@bp.get("/blockchain/provenance/<scan_id>")
def blockchain_provenance(scan_id: str):
    return success(_service().provenance(scan_id))


@bp.post("/blockchain/provenance")
def commit_blockchain_provenance():
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    payload = request.get_json(silent=False)
    scan_id = str(payload.get("scan_id", "")).strip()
    if not scan_id:
        raise ValidationError("scan_id is required")
    source = str(payload.get("source", "terminal")).lower()
    if source != "terminal":
        raise ValidationError("only terminal-originated provenance commits are accepted")
    return success(_service().record_scan(scan_id, g.correlation_id), status=202)
