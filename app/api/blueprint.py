"""Purpose: Aggregate the versioned REST API through Flask Blueprints.
Directory: app/api.
Dependencies: Flask Blueprint and route Blueprints.
Connection: Registered once by the application factory at /api/v1.
"""

from __future__ import annotations

from flask import Blueprint

from app.constants import API_PREFIX
from app.api.routes import VERSIONED_BLUEPRINTS

bp = Blueprint("api", __name__, url_prefix=API_PREFIX)
for child in VERSIONED_BLUEPRINTS:
    bp.register_blueprint(child)

__all__ = ["bp"]
