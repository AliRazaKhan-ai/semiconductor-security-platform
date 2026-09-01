"""Purpose: Validate all public REST and health API contracts.
Directory: tests/api.
Dependencies: Flask application fixture.
Connection: Protects terminal ingestion, system health, compliance,
blockchain, hardware, and integration endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient


def assert_json_response(response, expected_status: int = 200) -> dict[str, Any]:
    assert response.status_code == expected_status
    assert response.content_type.startswith("application/json")

    payload = response.get_json()

    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    "path",
    (
        "/health/live",
        "/health/ready",
        "/api/v1/system/status",
        "/api/v1/blockchain/status",
        "/api/v1/compliance/status",
    ),
)
def test_operational_get_endpoints_return_json(
    client: FlaskClient,
    path: str,
) -> None:
    response = client.get(path)
    payload = assert_json_response(response)

    assert payload


def test_liveness_endpoint_reports_alive(client: FlaskClient) -> None:
    payload = assert_json_response(client.get("/health/live"))

    assert payload.get("status") in {"alive", "ok", "healthy"}


def test_readiness_endpoint_contains_checks(client: FlaskClient) -> None:
    payload = assert_json_response(client.get("/health/ready"))

    assert payload["status"] in {"ready", "degraded"}
    assert isinstance(payload["checks"], list)


def test_system_status_uses_json_event_store(client: FlaskClient) -> None:
    payload = assert_json_response(
        client.get("/api/v1/system/status")
    )

    data = payload["data"]

    assert data["database"]["type"] == "json_event_store"
    assert data["database"]["sql_enabled"] is False
    assert data["authentication"]["enabled"] is False


def test_blockchain_status_has_fabric_and_ethereum(client: FlaskClient) -> None:
    payload = assert_json_response(
        client.get("/api/v1/blockchain/status")
    )

    data = payload["data"]

    assert "hyperledger_fabric" in data
    assert "ethereum_anchor" in data
    assert "storage_policy" in data


def test_compliance_status_is_fail_closed(client: FlaskClient) -> None:
    payload = assert_json_response(
        client.get("/api/v1/compliance/status")
    )

    data = payload["data"]

    assert data["enabled"] is True
    assert "fail_closed" in data["mode"]


def test_unknown_api_route_returns_controlled_404(
    client: FlaskClient,
) -> None:
    payload = assert_json_response(
        client.get("/api/v1/does-not-exist"),
        expected_status=404,
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_scan_submission_rejects_empty_json(client: FlaskClient) -> None:
    response = client.post("/api/v1/scans", json={})
    payload = assert_json_response(response, expected_status=400)

    assert payload["ok"] is False
    assert "error" in payload


def test_integration_run_requires_source_file(
    client: FlaskClient,
) -> None:
    response = client.post(
        "/api/v1/integration/run",
        json={},
    )

    payload = assert_json_response(response, expected_status=400)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_source_file"


def test_integration_run_rejects_non_json(client: FlaskClient) -> None:
    response = client.post(
        "/api/v1/integration/run",
        data="not-json",
        content_type="text/plain",
    )

    payload = assert_json_response(response, expected_status=400)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"
