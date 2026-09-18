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
    # Storage checks alone cannot see a subsystem that failed to construct. The
    # factory records those, so a server missing its hardware pipeline or ledger
    # reports degraded rather than ready.
    degraded = dict(app.extensions.get("semisecure.degraded") or {})
    healthy = all(check.healthy for check in checks) and not degraded

    if degraded:
        status = "degraded"
    elif healthy:
        status = "ready"
    else:
        status = "not_ready"

    return (
        {
            "status": status,
            "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "checks": [check.to_dict() for check in checks],
            "degraded_subsystems": degraded,
        },
        200 if healthy else 503,
    )

