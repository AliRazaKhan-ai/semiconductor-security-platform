"""Purpose: Verify initial dashboard projections remain compact and bounded.
Directory: tests/unit/dashboard.
Dependencies: pytest and dashboard read-model builder.
Connection: Protects the read-only server-rendered bootstrap contract.
"""

from app.dashboard.read_models import build_initial_dashboard_model


def test_initial_model_is_bounded_and_removes_unknown_fields() -> None:
    scans = [
        {
            "scan_id": f"scan-{index}",
            "chip_id": f"chip-{index}",
            "status": "APPROVED",
            "updated_at": "2026-07-14T10:00:00+00:00",
            "secret_internal_field": "must-not-be-rendered",
        }
        for index in range(5)
    ]
    model = build_initial_dashboard_model(scans, scan_count=500, limit=3)
    assert model.scan_count == 500
    assert len(model.scans) == 3
    assert all("secret_internal_field" not in item for item in model.scans)


def test_initial_model_enforces_a_positive_limit() -> None:
    model = build_initial_dashboard_model([], scan_count=0, limit=0)
    assert model.scans == ()
    assert model.scan_count == 0
