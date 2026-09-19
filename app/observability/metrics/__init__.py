"""Purpose: Expose platform state in Prometheus exposition format.
Directory: app/observability/metrics.
Dependencies: Flask, the event store reader, the degraded-subsystem record.
Connection: served at /metrics by the health blueprint.

RISK-09 / monitoring. The platform had health checks and structured logging and
nothing else: no counts, no durations, no way to see a trend. Values are read from
the event store when scraped rather than held in memory, so a restart does not reset
them and a second process would not disagree with the first.

Format is the Prometheus text exposition format. Nothing here requires a Prometheus
server; curl reads it as it stands.
"""

from __future__ import annotations

from typing import Any

from flask import Flask


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _line(metric: str, value: float, **labels: str) -> str:
    """Render one sample. The first parameter is `metric`, not `name`, so that a
    metric can carry a label called `name` without colliding with it."""
    if labels:
        rendered = ",".join(
            f'{key}="{_escape(str(val))}"' for key, val in sorted(labels.items())
        )
        return f"{metric}{{{rendered}}} {value}"
    return f"{metric} {value}"


def render_metrics(app: Flask) -> str:
    """Return the current platform state in Prometheus exposition format."""
    lines: list[str] = []

    config = app.config.get("PLATFORM_CONFIG", {})
    application = config.get("application", {})

    lines.append("# HELP semisecure_build_info Platform version and environment.")
    lines.append("# TYPE semisecure_build_info gauge")
    lines.append(
        _line(
            "semisecure_build_info",
            1,
            version=str(application.get("version", "unknown")),
            environment=str(
                config.get("environment")
                or application.get("environment")
                or app.config.get("ENV", "unknown")
            ),
        )
    )

    # A subsystem that failed to construct is recorded by the factory. Runtime callers
    # fail closed, but the absence is otherwise invisible outside /health/ready.
    degraded = dict(app.extensions.get("semisecure.degraded") or {})
    tracked = (
        "blockchain",
        "ai_pipeline",
        "hardware_pipeline",
        "compliance_service",
    )

    lines.append("")
    lines.append("# HELP semisecure_subsystem_up Subsystem constructed at startup.")
    lines.append("# TYPE semisecure_subsystem_up gauge")
    for name in tracked:
        lines.append(
            _line("semisecure_subsystem_up", 0 if name in degraded else 1, name=name)
        )

    events = app.extensions.get("semisecure.event_store")

    if events is None:
        lines.append("")
        lines.append("# event store unavailable; scan metrics omitted")
        return "\n".join(lines) + "\n"

    try:
        total = int(events.count_scans())
    except Exception:  # noqa: BLE001 - a scrape must never raise
        total = -1

    lines.append("")
    lines.append("# HELP semisecure_scans_total Scans recorded in the event store.")
    lines.append("# TYPE semisecure_scans_total gauge")
    lines.append(_line("semisecure_scans_total", total))

    # The decision and stage gauges were removed: events.latest returns event
    # snapshots, not run records, so deployment_decision is not on them and every
    # sample reported UNKNOWN. They also dominated the scrape time. Scan count and
    # subsystem status carry the useful signal and neither needs latest().
    return "\n".join(lines) + "\n"
