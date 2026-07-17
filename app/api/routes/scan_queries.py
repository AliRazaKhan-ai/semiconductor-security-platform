"""Purpose: Query scan summaries and immutable event histories.
Directory: app/api/routes.
Dependencies: Flask, EventStore.
Connection: Read-only dashboard and terminal diagnostics use these endpoints.
"""

from __future__ import annotations

from flask import Blueprint, request

from app.api.response import success
from app.exceptions import ValidationError
from app.extensions import event_store

bp = Blueprint("scan_queries", __name__)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"Query parameter '{name}' must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValidationError(
            f"Query parameter '{name}' is outside the allowed range",
            {"minimum": minimum, "maximum": maximum},
        )
    return value


@bp.get("/scans/latest")
def latest_scans():
    limit = _bounded_int("limit", 50, 1, 500)
    items = event_store().latest(limit)
    return success(items, meta={"count": len(items), "limit": limit})


@bp.get("/scans/<scan_id>")
def scan_summary(scan_id: str):
    return success(event_store().snapshot(scan_id))


@bp.get("/scans/<scan_id>/events")
def scan_events(scan_id: str):
    after_sequence = _bounded_int("after_sequence", 0, 0, 10_000_000)
    limit = _bounded_int("limit", 500, 1, 5000)
    events = event_store().events(scan_id, after_sequence=after_sequence, limit=limit)
    return success(
        [event.to_dict() for event in events],
        meta={"count": len(events), "after_sequence": after_sequence, "limit": limit},
    )

