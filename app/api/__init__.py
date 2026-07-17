"""Purpose: Public REST API Blueprint export.
Directory: app/api.
Dependencies: blueprint.
Connection: Registered by app.factory.
"""

from app.api.blueprint import bp

__all__ = ["bp"]

