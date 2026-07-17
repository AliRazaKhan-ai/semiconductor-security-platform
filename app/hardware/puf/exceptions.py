"""Purpose: Define fail-closed errors for the production PUF simulator.
Directory: app/hardware/puf.
Dependencies: app.exceptions.PlatformError.
Connection: Raised by PUF configuration, simulation, enrollment, authentication, and replay controls.
"""

from __future__ import annotations

from typing import Any

from app.exceptions import PlatformError


class PUFError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "puf_error", 500, details or {})


class PUFConfigurationError(PUFError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)
        self.code = "puf_configuration_error"


class PUFIntegrityError(PUFError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)
        self.code = "puf_integrity_error"


class PUFEnrollmentError(PUFError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)
        self.code = "puf_enrollment_error"
        self.status_code = 422


class PUFAuthenticationError(PUFError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)
        self.code = "puf_authentication_error"
        self.status_code = 403


class PUFReplayError(PUFAuthenticationError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)
        self.code = "puf_replay_detected"
