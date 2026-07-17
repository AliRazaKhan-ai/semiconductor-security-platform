"""Purpose: Serve read-only enterprise dashboard and evidence pages.
Directory: app/dashboard.
Dependencies: Flask templates, JSON EventStore, dashboard read models.
Connection: Pages consume read-only REST and SocketIO; no dashboard route mutates platform state.
"""

from __future__ import annotations

from typing import Any

from flask import current_app, render_template

from app.dashboard.blueprint import bp
from app.dashboard.read_models import DashboardReadModelReader, DashboardRuntimeConfig
from app.exceptions import NotFoundError
from app.extensions import event_store


def _runtime_config() -> DashboardRuntimeConfig:
    platform = current_app.config["PLATFORM_CONFIG"]
    dashboard = platform.get("dashboard", {})
    api_prefix = str(platform.get("api", {}).get("prefix", "/api/v1"))
    return DashboardRuntimeConfig(
        api_prefix=api_prefix,
        socket_namespace=str(platform["websocket"]["namespace"]),
        refresh_interval_ms=max(3000, int(dashboard.get("refresh_interval_ms", 5000))),
        initial_scan_limit=max(1, min(int(dashboard.get("initial_scan_limit", 20)), 100)),
    )


def _base_context(*, active_page: str, include_initial_scans: bool = False) -> dict[str, Any]:
    platform = current_app.config["PLATFORM_CONFIG"]
    runtime = _runtime_config()
    initial_scans: list[dict[str, Any]] = []
    if include_initial_scans:
        model = DashboardReadModelReader(event_store()).initial(runtime.initial_scan_limit)
        initial_scans = list(model.scans)
    return {
        "application": dict(platform["application"]),
        "environment": current_app.config["ENVIRONMENT"],
        "dashboard_config": runtime.to_dict(),
        "initial_scans": initial_scans,
        "active_page": active_page,
    }


@bp.get("/")
@bp.get("/dashboard")
def dashboard() -> str:
    return render_template(
        "dashboard.html",
        **_base_context(active_page="dashboard", include_initial_scans=True),
    )


@bp.get("/dashboard/scans/<scan_id>")
def scan_detail(scan_id: str) -> tuple[str, int] | str:
    try:
        scan = event_store().snapshot(scan_id)
        status = 200
    except NotFoundError:
        scan = None
        status = 404
    rendered = render_template(
        "scan_detail.html",
        scan=scan,
        **_base_context(active_page="dashboard"),
    )
    return rendered if status == 200 else (rendered, status)


@bp.get("/dashboard/chips/<chip_id>")
def chip_history(chip_id: str) -> str:
    return render_template(
        "chip_history.html",
        chip_id=chip_id,
        events=event_store().chip_history(chip_id),
        **_base_context(active_page="dashboard"),
    )


@bp.get("/dashboard/system")
def system_health() -> str:
    return render_template(
        "system_health.html",
        **_base_context(active_page="system"),
    )


@bp.get("/dashboard/provenance/<scan_id>")
def provenance(scan_id: str) -> tuple[str, int] | str:
    try:
        scan = event_store().snapshot(scan_id)
        status = 200
    except NotFoundError:
        scan = None
        status = 404
    rendered = render_template(
        "provenance.html",
        scan=scan,
        **_base_context(active_page="dashboard"),
    )
    return rendered if status == 200 else (rendered, status)
