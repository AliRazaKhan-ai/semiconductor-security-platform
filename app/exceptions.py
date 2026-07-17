"""Purpose: Define typed platform exceptions and HTTP mappings.
Directory: app.
Dependencies: Python standard library.
Connection: Raised by storage, configuration, validation, and API services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformError(Exception):
    message: str
    code: str = "platform_error"
    status_code: int = 500
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class ConfigurationError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "configuration_error", 500, details or {})


class ValidationError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "validation_error", 400, details or {})


class NotFoundError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "not_found", 404, details or {})


class ConflictError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "conflict", 409, details or {})


class EventStoreError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "event_store_error", 500, details or {})


class IntegrityError(PlatformError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "integrity_error", 500, details or {})


class RateLimitError(PlatformError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "Request rate limit exceeded",
            "rate_limit_exceeded",
            429,
            {"retry_after_seconds": retry_after},
        )

