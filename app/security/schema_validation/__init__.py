"""Purpose: Public JSON schema validation exports.
Directory: app/security/schema_validation.
Dependencies: registry and validator.
Connection: Imported by REST routes.
"""

from app.security.schema_validation.validator import validate_payload

__all__ = ["validate_payload"]

