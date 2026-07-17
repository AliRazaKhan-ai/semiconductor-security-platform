"""Purpose: Build safe, compact initial dashboard projections from JSON event-store indexes.
Directory: app/dashboard/read_models.
Dependencies: dashboard read-model schemas.
Connection: Reduces server-rendered payload size while REST remains authoritative after page load.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.dashboard.read_models.schemas import InitialDashboardModel

_ALLOWED_FIELDS = (
    "scan_id",
    "chip_id",
    "updated_at",
    "status",
    "current_stage",
    "last_event_type",
    "last_event_hash",
    "last_sequence",
    "event_count",
    "latest_payload",
)


def _compact_scan(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in _ALLOWED_FIELDS if key in value}


def build_initial_dashboard_model(
    scans: Iterable[Mapping[str, Any]],
    *,
    scan_count: int,
    limit: int,
) -> InitialDashboardModel:
    bounded_limit = max(1, min(int(limit), 100))
    compact = tuple(_compact_scan(item) for item in list(scans)[:bounded_limit])
    return InitialDashboardModel(scans=compact, scan_count=max(0, int(scan_count)))
