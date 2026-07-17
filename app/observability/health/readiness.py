"""Purpose: Aggregate dependency checks into a readiness decision.
Directory: app/observability/health.
Dependencies: Flask, health checks.
Connection: Exposed at /health/ready and included in system status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import Flask

from app.observability.health.checks import run_readiness_checks


def readiness_payload(app: Flask) -> tuple[dict[str, Any], int]:
    checks = run_readiness_checks(app)
    healthy = all(check.healthy for check in checks)
    return (
        {
            "status": "ready" if healthy else "not_ready",
            "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "checks": [check.to_dict() for check in checks],
        },
        200 if healthy else 503,
    )

