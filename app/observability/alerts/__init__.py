"""Purpose: Evaluate alert rules against current platform state.
Directory: app/observability/alerts.
Dependencies: Flask, the drift observation log, the degraded-subsystem record.
Connection: served at /alerts by the health blueprint; also logged.

RISK-09 / alerting. Metrics report state; nothing said when the state was wrong.
The backend died three times during testing and was noticed only when a scan failed.

Rules read the same values /metrics exposes, so monitoring and alerting cannot
disagree. Evaluation happens on request rather than on a timer: a background thread
in a single gevent worker is a reliability risk for no gain, and a Prometheus
deployment would evaluate rules against the same endpoint anyway.

Nothing here raises. An alert evaluator that breaks the application it watches is
worse than no evaluator.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask

DRIFT_LOG = Path("evidence/ai/drift/drift_observations.jsonl")
DRIFT_WINDOW_HOURS = 24
DRIFT_WARNING_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class Alert:
    rule: str
    severity: str
    summary: str
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _subsystem_alerts(app: Flask) -> list[Alert]:
    """A subsystem that failed to construct. Runtime callers fail closed, so this is
    a loss of capability rather than an unsafe state, but it is invisible otherwise."""
    degraded = dict(app.extensions.get("semisecure.degraded") or {})

    return [
        Alert(
            rule="SUBSYSTEM_DOWN",
            severity="critical",
            summary=f"{name} failed to construct at startup",
            detail={"subsystem": name, "error": str(error)},
        )
        for name, error in sorted(degraded.items())
    ]


def _drift_alerts() -> list[Alert]:
    """Repeated drift observations mean the models are being asked about a
    distribution they were not trained on. Reported, never used to decide."""
    if not DRIFT_LOG.is_file():
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=DRIFT_WINDOW_HOURS)
    recent: list[dict[str, Any]] = []

    try:
        for line in DRIFT_LOG.read_text(encoding="utf-8").splitlines()[-500:]:
            if not line.strip():
                continue
            entry = json.loads(line)
            observed = entry.get("observed_at_utc", "")
            try:
                when = datetime.fromisoformat(observed)
            except ValueError:
                continue
            if when >= cutoff:
                recent.append(entry)
    except (OSError, json.JSONDecodeError):
        return []

    if not recent:
        return []

    drifted = [e for e in recent if e.get("status") == "DRIFT"]

    if drifted:
        worst = max(drifted, key=lambda e: float(e.get("worst_deviation", 0)))
        return [
            Alert(
                rule="DRIFT_DETECTED",
                severity="critical",
                summary=(
                    f"{len(drifted)} feature-drift observations in "
                    f"{DRIFT_WINDOW_HOURS}h, worst {worst.get('worst_feature')}"
                ),
                detail={
                    "observations": len(drifted),
                    "worst_feature": worst.get("worst_feature"),
                    "worst_deviation": worst.get("worst_deviation"),
                },
            )
        ]

    warnings = [e for e in recent if e.get("status") == "WARNING"]

    if len(warnings) >= DRIFT_WARNING_THRESHOLD:
        worst = max(warnings, key=lambda e: float(e.get("worst_deviation", 0)))
        return [
            Alert(
                rule="DRIFT_WARNING",
                severity="warning",
                summary=(
                    f"{len(warnings)} feature-drift warnings in "
                    f"{DRIFT_WINDOW_HOURS}h, worst {worst.get('worst_feature')}"
                ),
                detail={
                    "observations": len(warnings),
                    "worst_feature": worst.get("worst_feature"),
                    "worst_deviation": worst.get("worst_deviation"),
                },
            )
        ]

    return []


def _storage_alerts(app: Flask) -> list[Alert]:
    """A store the platform cannot write is a loss of the audit trail."""
    from app.observability.health import run_readiness_checks

    try:
        checks = run_readiness_checks(app)
    except Exception:  # noqa: BLE001 - evaluation must not raise
        return []

    return [
        Alert(
            rule="STORAGE_UNAVAILABLE",
            severity="critical",
            summary=f"{check.name} is {check.status}",
            detail=check.to_dict(),
        )
        for check in checks
        if not check.healthy
    ]


def evaluate_alerts(app: Flask) -> list[Alert]:
    """Return every firing alert. Never raises."""
    alerts: list[Alert] = []

    for rule in (_subsystem_alerts, _storage_alerts):
        try:
            alerts.extend(rule(app))
        except Exception:  # noqa: BLE001
            continue

    try:
        alerts.extend(_drift_alerts())
    except Exception:  # noqa: BLE001
        pass

    return alerts
