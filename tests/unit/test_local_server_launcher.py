"""Ensure the local demonstration server can start without debug mode."""

from pathlib import Path


def test_local_launcher_allows_werkzeug() -> None:
    source = Path("manage.py").read_text(encoding="utf-8")

    assert "allow_unsafe_werkzeug=True" in source
    assert "allow_unsafe_werkzeug=debug" not in source
