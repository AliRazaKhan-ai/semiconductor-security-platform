"""Purpose: Validate approved fail-closed and terminal-controlled security rules.
Directory: tests/security.
Dependencies: source tree, Flask client and configuration files.
Connection: Ensures the implementation remains aligned with the approved
exam architecture: no login, no JWT, no SQL, read-only dashboard and
terminal-only scan submission.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


FORBIDDEN_DEPENDENCIES = (
    "flask-jwt-extended",
    "sqlalchemy",
    "flask-sqlalchemy",
    "psycopg",
    "psycopg2",
    "postgresql",
)


def test_forbidden_auth_and_sql_dependencies_are_absent() -> None:
    requirements = (
        ROOT / "requirements.txt"
    ).read_text(encoding="utf-8").lower()

    for dependency in FORBIDDEN_DEPENDENCIES:
        assert dependency not in requirements


def test_no_login_or_user_management_routes() -> None:
    from app import create_app

    app = create_app({"TESTING": True})

    routes = {
        str(rule).lower()
        for rule in app.url_map.iter_rules()
    }

    forbidden_tokens = (
        "/login",
        "/logout",
        "/register",
        "/users",
        "/auth/token",
        "/auth/refresh",
    )

    for route in routes:
        for token in forbidden_tokens:
            assert token not in route


def test_environment_file_is_gitignored() -> None:
    gitignore = (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8").splitlines()

    assert ".env" in {
        line.strip()
        for line in gitignore
    }


def test_private_runtime_and_blockchain_state_are_gitignored() -> None:
    gitignore = (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")

    required_rules = (
        "runtime/*",
        "data/blockchain/anvil-state.json",
        "data/blockchain/ethereum_receipts/",
        "data/event_store/",
        "data/compliance/decisions/",
    )

    for rule in required_rules:
        assert rule in gitignore


def test_no_obvious_private_key_is_committed_in_application_source() -> None:
    key_pattern = re.compile(
        r"\b[0-9a-fA-F]{64}\b"
    )

    allowed_roots = (
        ROOT / "app",
        ROOT / "configs",
        ROOT / "scripts",
    )

    suspicious: list[str] = []

    for source_root in allowed_roots:
        for path in source_root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix not in {
                ".py",
                ".json",
                ".sh",
                ".yaml",
                ".yml",
            }:
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            for match in key_pattern.findall(text):
                if match == "0" * 64:
                    continue

                nearby = text.lower()

                if (
                    "private_key" in nearby
                    or "private key" in nearby
                ):
                    suspicious.append(str(path))
                    break

    assert not suspicious, (
        "Possible committed private key material: "
        + ", ".join(sorted(set(suspicious)))
    )


def test_error_responses_do_not_expose_python_traceback(client) -> None:
    response = client.get("/api/v1/nonexistent-security-test")
    text = response.get_data(as_text=True)

    assert response.status_code == 404
    assert "Traceback (most recent call last)" not in text
    assert 'File "' not in text


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/system/status",
        "/api/v1/blockchain/status",
        "/api/v1/compliance/status",
    ),
)
def test_sensitive_status_endpoints_reject_unsupported_methods(
    client,
    path: str,
) -> None:
    response = client.delete(path)

    assert response.status_code in {404, 405}


def test_event_store_paths_are_not_web_accessible(client) -> None:
    response = client.get(
        "/data/event_store/index.json"
    )

    assert response.status_code in {404, 403}


def test_safe_cleanup_does_not_delete_fabric_volumes() -> None:
    source = (
        ROOT / "scripts" / "maintenance" / "safe_cleanup.sh"
    ).read_text(encoding="utf-8")

    assert "docker volume prune" not in source
    assert "docker container prune" not in source


def test_pipeline_contains_fail_closed_controls() -> None:
    """Verify infrastructure failure, stop and quarantine controls exist."""
    source = (
        ROOT / "app" / "pipeline" / "orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "INFRASTRUCTURE_HOLD" in source
    assert "HOLD_PENDING_BLOCKCHAIN_RECOVERY" in source
    assert "stop_pipeline" in source

    normalised = source.lower()

    assert "quarantine" in normalised
    assert "deployment_decision" in normalised


def test_logging_configuration_has_bounded_rotation() -> None:
    config = json.loads(
        (
            ROOT / "configs" / "application" / "logging.json"
        ).read_text(encoding="utf-8")
    )

    assert config["max_bytes"] <= 5_242_880
    assert config["backup_count"] <= 3
