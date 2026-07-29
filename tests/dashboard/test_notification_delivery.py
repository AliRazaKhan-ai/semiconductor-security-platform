"""Regression contracts for dashboard notification delivery."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_socket_publisher_broadcasts_namespace_events() -> None:
    source = (
        ROOT / "app/websocket/publisher.py"
    ).read_text(encoding="utf-8")

    assert '"platform.event"' in source
    assert 'to="all"' not in source
    assert 'to=f"scan:{record.scan_id}"' in source


def test_dashboard_has_rest_notification_fallback() -> None:
    source = (
        ROOT / "app/dashboard/static/js/dashboard.js"
    ).read_text(encoding="utf-8")

    assert "notificationSignatures: new Map()" in source
    assert "function syncRestNotifications(scans)" in source
    assert "syncRestNotifications(orderedScans())" in source
    assert "No backend events received" not in source
