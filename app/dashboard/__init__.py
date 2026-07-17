"""Purpose: Lazily export the read-only dashboard Blueprint.
Directory: app/dashboard.
Dependencies: dashboard.blueprint only when Flask application composition requests ``bp``.
Connection: Keeps read-model modules importable in tooling that does not install Flask.
"""

from __future__ import annotations

from typing import Any

__all__ = ["bp"]


def __getattr__(name: str) -> Any:
    if name == "bp":
        from app.dashboard.blueprint import bp

        return bp
    raise AttributeError(name)
