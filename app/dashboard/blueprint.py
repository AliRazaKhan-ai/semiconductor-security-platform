"""Purpose: Define the read-only dashboard Blueprint.
Directory: app/dashboard.
Dependencies: Flask Blueprint.
Connection: Registered by the factory; delegates page routes to dashboard.views.
"""

from __future__ import annotations

from flask import Blueprint

bp = Blueprint(
    "dashboard",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/dashboard/static",
)

from app.dashboard import views as _views

__all__ = ["bp"]

