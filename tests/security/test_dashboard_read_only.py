from __future__ import annotations


def test_dashboard_has_no_write_route(client) -> None:
    assert client.get("/dashboard").status_code == 200
    assert client.post("/dashboard", json={}).status_code == 405
    assert client.post("/api/v1/system/status", json={}).status_code == 405


def test_no_login_or_authentication_routes(client) -> None:
    assert client.get("/login").status_code == 404
    assert client.post("/auth/login", json={}).status_code == 404

