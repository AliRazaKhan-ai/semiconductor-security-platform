"""Purpose: Export dashboard read-model contracts and reader.
Directory: app/dashboard/read_models.
Dependencies: builder, reader, schemas.
Connection: Imported by dashboard views and unit tests.
"""

from app.dashboard.read_models.builder import build_initial_dashboard_model
from app.dashboard.read_models.reader import DashboardReadModelReader
from app.dashboard.read_models.schemas import DashboardRuntimeConfig, InitialDashboardModel

__all__ = [
    "DashboardReadModelReader",
    "DashboardRuntimeConfig",
    "InitialDashboardModel",
    "build_initial_dashboard_model",
]
