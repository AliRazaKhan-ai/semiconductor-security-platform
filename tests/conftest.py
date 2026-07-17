"""Shared fixtures for the Flask backend test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEMISURE_ENV", "test")
    monkeypatch.setenv("SEMISURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SEMISURE_RUNTIME_DIR", str(tmp_path / "runtime"))
    from app.factory import create_app

    application = create_app({"TESTING": True})
    yield application


@pytest.fixture
def client(app):
    return app.test_client()

