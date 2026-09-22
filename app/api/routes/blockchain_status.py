"""Read-only blockchain status, provenance queries, and terminal-triggered provenance commit."""
from __future__ import annotations

from flask import Blueprint, current_app, g, request

from app.api.response import success
from werkzeug.exceptions import ServiceUnavailable

from app.exceptions import NotFoundError, ValidationError

bp = Blueprint("blockchain_status", __name__)


def _service():
    service = current_app.extensions.get("semisecure.blockchain_service")
    if service is None:
        # 503, not 500: the service is absent, the server is not broken.
        raise ServiceUnavailable("blockchain service is unavailable")
    return service


@bp.get("/blockchain/status")
def blockchain_status():
    # This route raised when the service had not constructed, returning 500 whenever
    # no signing key was configured or Fabric was unreachable at startup. Its own test
    # says the status contract must hold in all environments, so an absent service is
    # reported, with the reason the factory recorded, rather than raised.
    service = current_app.extensions.get("semisecure.blockchain_service")
    if service is None:
        reason = (current_app.extensions.get("semisecure.degraded") or {}).get(
            "blockchain", "blockchain service was not constructed"
        )
        return success(
            {
                "available": False,
                "reason": reason,
                "hyperledger_fabric": {"enabled": False, "connection_state": "unavailable"},
                "ethereum_anchor": {"enabled": False, "connection_state": "unavailable"},
                "storage_policy": {
                    "ethereum": "bytes32 SHA-256 Merkle roots only",
                    "fabric": "complete provenance, evidence hashes, decisions, and private collections",
                },
            }
        )
    return success(service.status())


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
