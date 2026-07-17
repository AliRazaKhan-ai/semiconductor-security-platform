"""Purpose: Expose liveness and readiness probes outside the versioned API.
Directory: app/api/routes.
Dependencies: Flask, health payloads.
Connection: Used by systemd, Docker, Kubernetes, and reverse proxies.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.observability.health import liveness_payload, readiness_payload

bp = Blueprint("health", __name__)


@bp.get("/health/live")
def live():
    return jsonify(liveness_payload()), 200


@bp.get("/health/ready")
def ready():
    payload, status = readiness_payload(current_app)
    return jsonify(payload), status

