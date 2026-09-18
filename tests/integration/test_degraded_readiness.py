"""Purpose: Assert that a subsystem which fails to construct is reported, not hidden.
Directory: tests/integration.
Dependencies: pytest, app.create_app.
Connection: Guards RISK-16. create_app builds subsystems in try/except so a missing
dependency does not stop the process. Before this, the failure was a log warning and
/health/ready still said "ready": the application was observed running with
hardware_pipeline and blockchain both absent while reporting itself healthy.
"""

from __future__ import annotations

import pytest

from app import create_app


@pytest.mark.security
def test_readiness_names_a_subsystem_that_failed_to_construct(monkeypatch) -> None:
    monkeypatch.setenv("SEMISURE_OPENTITAN_VERIFICATION_KEY", "")

    app = create_app()

    assert "hardware_pipeline" in app.extensions.get("semisecure.degraded", {})

    with app.test_client() as client:
        response = client.get("/health/ready")
        body = response.get_json()

    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert "hardware_pipeline" in body["degraded_subsystems"]


@pytest.mark.security
def test_readiness_is_ready_when_every_subsystem_constructs() -> None:
    """The guard above must not pass by always reporting degraded."""
    app = create_app()

    with app.test_client() as client:
        body = client.get("/health/ready").get_json()

    assert body["status"] in {"ready", "degraded"}
    if body["status"] == "ready":
        assert body["degraded_subsystems"] == {}
