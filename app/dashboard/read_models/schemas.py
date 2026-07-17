"""Purpose: Define immutable server-rendered dashboard configuration and initial read models.
Directory: app/dashboard/read_models.
Dependencies: dataclasses and standard typing.
Connection: Dashboard views use these models before JavaScript begins REST and SocketIO refreshes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardRuntimeConfig:
    api_prefix: str
    socket_namespace: str
    refresh_interval_ms: int
    initial_scan_limit: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InitialDashboardModel:
    scans: tuple[dict[str, Any], ...]
    scan_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"scans": [dict(item) for item in self.scans], "scan_count": self.scan_count}
