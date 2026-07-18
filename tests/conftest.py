"""Shared fixtures for the Flask backend test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env", override=False)


@pytest.fixture
def app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator:
    """Create an isolated Flask test application."""
    monkeypatch.setenv("SEMISURE_ENV", "test")
    monkeypatch.setenv(
        "SEMISURE_DATA_DIR",
        str(tmp_path / "data"),
    )
    monkeypatch.setenv(
        "SEMISURE_RUNTIME_DIR",
        str(tmp_path / "runtime"),
    )

    from app.factory import create_app

    application = create_app(
        {
            "TESTING": True,
        }
    )

    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()
