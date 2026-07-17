"""Purpose: Validate non-secret JSON configuration structure.
Directory: app/storage/config_store.
Dependencies: app.exceptions.
Connection: Called by the configuration loader before Flask receives settings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.exceptions import ConfigurationError


def require_mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            f"Configuration section '{key}' must be a JSON object",
            {"section": key},
        )
    return value


def require_value(
    config: Mapping[str, Any],
    key: str,
    expected_type: type[Any] | tuple[type[Any], ...],
) -> Any:
    if key not in config:
        raise ConfigurationError(f"Missing configuration key '{key}'", {"key": key})
    value = config[key]
    if not isinstance(value, expected_type):
        expected = (
            expected_type.__name__
            if isinstance(expected_type, type)
            else ", ".join(item.__name__ for item in expected_type)
        )
        raise ConfigurationError(
            f"Configuration key '{key}' has the wrong type",
            {"key": key, "expected": expected, "actual": type(value).__name__},
        )
    return value


def validate_platform_config(config: Mapping[str, Any]) -> None:
    application = require_mapping(config, "application")
    storage = require_mapping(config, "storage")
    websocket = require_mapping(config, "websocket")
    logging_config = require_mapping(config, "logging")
    security = require_mapping(config, "security")

    require_value(application, "name", str)
    require_value(application, "version", str)
    require_value(application, "host", str)
    require_value(application, "port", int)
    require_value(application, "max_content_length", int)
    require_value(storage, "event_store_root", str)
    require_value(storage, "index_root", str)
    require_value(storage, "snapshot_root", str)
    require_value(storage, "audit_root", str)
    require_value(storage, "lock_root", str)
    require_value(websocket, "namespace", str)
    require_value(websocket, "cors_allowed_origins", list)
    require_value(logging_config, "level", str)
    require_mapping(security, "authentication")

    if application["port"] <= 0 or application["port"] > 65535:
        raise ConfigurationError("Application port must be between 1 and 65535")
    if application["max_content_length"] <= 0:
        raise ConfigurationError("Maximum content length must be positive")

