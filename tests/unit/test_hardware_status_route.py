"""Purpose: Ensure the hardware status endpoint uses the correct API prefix.
Directory: tests/unit.
Dependencies: app.create_app.
Connection: Prevents duplicate /api/v1 prefixes during blueprint registration.
"""

from app import create_app


def test_hardware_status_route_has_single_api_prefix() -> None:
    app = create_app()

    routes = {str(rule) for rule in app.url_map.iter_rules()}

    assert "/api/v1/hardware/status" in routes
    assert "/api/v1/api/v1/hardware/status" not in routes
