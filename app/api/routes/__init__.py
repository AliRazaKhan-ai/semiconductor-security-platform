from app.api.routes.integration import bp as integration_bp
"""Purpose: Export all REST route Blueprints.
Directory: app/api/routes.
Dependencies: route modules.
Connection: app.api.blueprint registers versioned routes; app.factory registers health directly.
"""

from app.api.routes.blockchain_status import bp as blockchain_status_bp
from app.api.routes.chip_history import bp as chip_history_bp
from app.api.routes.health import bp as health_bp
from app.api.routes.scan_queries import bp as scan_queries_bp
from app.api.routes.scan_submission import bp as scan_submission_bp
from app.api.routes.system_status import bp as system_status_bp
from app.api.routes.hardware_status import bp as hardware_status_bp

VERSIONED_BLUEPRINTS = (
    integration_bp,
    scan_submission_bp,
    scan_queries_bp,
    chip_history_bp,
    blockchain_status_bp,
    system_status_bp,
    hardware_status_bp,
)

__all__ = ["VERSIONED_BLUEPRINTS", "health_bp", "hardware_status_bp"]
