"""Purpose: Pin the conditions under which unauthenticated scan submission is acceptable.
Directory: tests/static.
Dependencies: pytest, json, re, pathlib.
Connection: RISK-14. POST /api/v1/scans accepts submissions with no authentication,
against the terminal-controlled design principle in README.md. It is accepted because
the service binds loopback in every environment and SECURITY.md requires a controlled
network in front of it. These tests fail if either condition stops holding, so the
acceptance is re-evaluated rather than inherited.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ROOT / "configs" / "environments"


@pytest.mark.security
def test_every_environment_binds_loopback() -> None:
    bound = {}

    for path in sorted(ENVIRONMENTS.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        host = (config.get("application") or config).get("host")
        if host is not None:
            bound[path.name] = host

    assert bound, f"no environment config declares a host under {ENVIRONMENTS}"

    external = {name: host for name, host in bound.items() if host not in
                {"127.0.0.1", "localhost", "::1"}}

    assert not external, (
        "Scan submission is unauthenticated and is accepted only because the "
        f"service is not reachable off-host. These bind externally: {external}. "
        "Either bind loopback or put authentication in front of the endpoint."
    )


@pytest.mark.security
def test_the_submission_switch_still_exists() -> None:
    """The endpoint can be closed without code changes if the scope changes."""
    source = (ROOT / "app" / "api" / "routes" / "scan_submission.py").read_text(
        encoding="utf-8"
    )

    assert "scan_submission_enabled" in source, (
        "The guard that allows submission to be disabled has gone. RISK-14 was "
        "accepted partly because closing the endpoint is a config change."
    )


@pytest.mark.security
def test_security_documents_the_deployment_boundary() -> None:
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()

    assert "public internet" in security, (
        "SECURITY.md no longer states the deployment boundary that RISK-14 relies on."
    )
