"""Purpose: Provide a consolidated backend operational status response.
Directory: app/api/routes.
Dependencies: Flask, EventStore, readiness checks.
Connection: Powers dashboard health panels and deployment monitoring.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, current_app

from app.api.response import success
from app.extensions import event_store
from app.observability.health import readiness_payload

bp = Blueprint("system_status", __name__)


@bp.get("/system/status")
def system_status():
    readiness, readiness_code = readiness_payload(current_app)
    application = current_app.config["PLATFORM_CONFIG"]["application"]
    return success(
        {
            "application": {
                "name": application["name"],
                "version": application["version"],
                "environment": current_app.config["ENVIRONMENT"],
                "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
            "readiness": readiness,
            "readiness_http_status": readiness_code,
            "event_store": {"scan_count": event_store().count_scans()},
            "authentication": {"enabled": False},
            "database": {"type": "json_event_store", "sql_enabled": False},
        }
    )

