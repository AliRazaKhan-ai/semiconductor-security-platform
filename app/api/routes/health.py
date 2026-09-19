"""Purpose: Expose liveness and readiness probes outside the versioned API.
Directory: app/api/routes.
Dependencies: Flask, health payloads.
Connection: Used by systemd, Docker, Kubernetes, and reverse proxies.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify

from app.observability.health import liveness_payload, readiness_payload
from app.observability.metrics import render_metrics

bp = Blueprint("health", __name__)


@bp.get("/health/live")
def live():
    return jsonify(liveness_payload()), 200


@bp.get("/health/ready")
def ready():
    payload, status = readiness_payload(current_app)
    return jsonify(payload), status


@bp.get("/metrics")
def metrics():
    """Platform state in Prometheus exposition format.

    Values are read from the event store when scraped rather than held in memory, so
    a restart does not reset them. Sits beside the health routes: read-only, GET only,
    no authentication, loopback-bound like the rest of the read surface.
    """
    return Response(
        render_metrics(current_app),
        mimetype="text/plain; version=0.0.4; charset=utf-8",
    )
