"""Purpose: Public package entry point for the Flask backend.
Directory: app.
Dependencies: app.factory.
Connection: Exposes create_app for Flask and Gunicorn discovery.
"""

from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any):
    from app.factory import create_app as factory_create_app

    return factory_create_app(*args, **kwargs)

__all__ = ["create_app"]

