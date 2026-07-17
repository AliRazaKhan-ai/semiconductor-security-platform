"""Purpose: Read initial dashboard projections from the authoritative JSON event store.
Directory: app/dashboard/read_models.
Dependencies: EventStore facade and dashboard builder.
Connection: Flask views use this reader; browser clients subsequently use read-only REST and SocketIO.
"""

from __future__ import annotations

from app.dashboard.read_models.builder import build_initial_dashboard_model
from app.dashboard.read_models.schemas import InitialDashboardModel
from app.storage.event_store import EventStore


class DashboardReadModelReader:
    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store

    def initial(self, limit: int = 20) -> InitialDashboardModel:
        return build_initial_dashboard_model(
            self.event_store.latest(limit),
            scan_count=self.event_store.count_scans(),
            limit=limit,
        )
