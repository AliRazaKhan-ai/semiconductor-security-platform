"""Purpose: Execute deterministic dependency health checks.
Directory: app/observability/health.
Dependencies: pathlib, os, EventStore.
Connection: Used by liveness, readiness, and system-status REST endpoints.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from flask import Flask


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    healthy: bool
    status: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def directory_check(name: str, path: Path) -> HealthCheckResult:
    try:
        path.mkdir(parents=True, exist_ok=True)
        writable = os.access(path, os.R_OK | os.W_OK | os.X_OK)
        return HealthCheckResult(
            name=name,
            healthy=writable,
            status="available" if writable else "permission_denied",
            details={"path": str(path)},
        )
    except OSError as exc:
        return HealthCheckResult(name, False, "unavailable", {"path": str(path), "reason": str(exc)})


def run_readiness_checks(app: Flask) -> list[HealthCheckResult]:
    checks = [
        directory_check("event_store", Path(app.config["EVENT_STORE_ROOT"])),
        directory_check("indexes", Path(app.config["INDEX_ROOT"])),
        directory_check("snapshots", Path(app.config["SNAPSHOT_ROOT"])),
        directory_check("audit", Path(app.config["AUDIT_ROOT"])),
        directory_check("locks", Path(app.config["LOCK_ROOT"])),
    ]
    event_store = app.extensions.get("semisecure.event_store")
    checks.append(
        HealthCheckResult(
            name="event_store_extension",
            healthy=event_store is not None,
            status="initialised" if event_store is not None else "missing",
            details={},
        )
    )
    return checks

