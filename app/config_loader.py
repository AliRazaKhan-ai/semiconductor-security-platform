"""Purpose: Build Flask-compatible settings from JSON and environment variables.
Directory: app.
Dependencies: pathlib, os, app.storage.config_store.
Connection: Called before Flask creation and before logging initialisation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.constants import DEFAULT_ENVIRONMENT
from app.exceptions import ConfigurationError
from app.storage.config_store import (
    deep_merge,
    load_directory,
    load_json_file,
    validate_platform_config,
)
from app.types import JSONObject


@dataclass(frozen=True, slots=True)
class LoadedConfiguration:
    environment: str
    project_root: Path
    config_root: Path
    values: JSONObject

    def flask_mapping(self) -> dict[str, Any]:
        application = self.values["application"]
        websocket = self.values["websocket"]
        storage = self.values["storage"]
        return {
            "PLATFORM_CONFIG": self.values,
            "ENVIRONMENT": self.environment,
            "PROJECT_ROOT": self.project_root,
            "CONFIG_ROOT": self.config_root,
            "HOST": application["host"],
            "PORT": application["port"],
            "DEBUG": application["debug"],
            "TESTING": application["testing"],
            "MAX_CONTENT_LENGTH": application["max_content_length"],
            "JSON_SORT_KEYS": application["json_sort_keys"],
            "SOCKETIO_NAMESPACE": websocket["namespace"],
            "EVENT_STORE_ROOT": self.project_root / storage["event_store_root"],
            "INDEX_ROOT": self.project_root / storage["index_root"],
            "SNAPSHOT_ROOT": self.project_root / storage["snapshot_root"],
            "AUDIT_ROOT": self.project_root / storage["audit_root"],
            "LOCK_ROOT": self.project_root / storage["lock_root"],
        }


def _parse_origins(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_environment_overrides(values: JSONObject) -> JSONObject:
    overrides: JSONObject = {}

    application: JSONObject = {}
    if host := os.getenv("SEMISURE_HOST"):
        application["host"] = host
    if port := os.getenv("SEMISURE_PORT"):
        try:
            application["port"] = int(port)
        except ValueError as exc:
            raise ConfigurationError("SEMISURE_PORT must be an integer") from exc
    if max_content := os.getenv("SEMISURE_MAX_CONTENT_LENGTH"):
        try:
            application["max_content_length"] = int(max_content)
        except ValueError as exc:
            raise ConfigurationError("SEMISURE_MAX_CONTENT_LENGTH must be an integer") from exc
    if application:
        overrides["application"] = application

    logging_override: JSONObject = {}
    if log_level := os.getenv("SEMISURE_LOG_LEVEL"):
        logging_override["level"] = log_level.upper()
    if logging_override:
        overrides["logging"] = logging_override

    storage_override: JSONObject = {}
    if data_dir := os.getenv("SEMISURE_DATA_DIR"):
        clean = data_dir.rstrip("/")
        storage_override.update(
            {
                "data_root": clean,
                "event_store_root": f"{clean}/event_store",
                "index_root": f"{clean}/indexes",
                "snapshot_root": f"{clean}/snapshots",
                "audit_root": f"{clean}/audit",
            }
        )
    if runtime_dir := os.getenv("SEMISURE_RUNTIME_DIR"):
        storage_override["lock_root"] = f"{runtime_dir.rstrip('/')}/locks"
    if storage_override:
        overrides["storage"] = storage_override

    websocket_override: JSONObject = {}
    if origins := os.getenv("SEMISURE_ALLOWED_ORIGINS"):
        websocket_override["cors_allowed_origins"] = _parse_origins(origins)
    if mode := os.getenv("SEMISURE_SOCKETIO_ASYNC_MODE"):
        websocket_override["async_mode"] = mode
    if websocket_override:
        overrides["websocket"] = websocket_override

    return deep_merge(values, overrides)


def load_platform_configuration(project_root: Path | None = None) -> LoadedConfiguration:
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    environment = os.getenv("SEMISURE_ENV", DEFAULT_ENVIRONMENT).strip().lower()
    config_dir_value = os.getenv("SEMISURE_CONFIG_DIR", "configs")
    config_root = Path(config_dir_value)
    if not config_root.is_absolute():
        config_root = root / config_root
    config_root = config_root.resolve()

    base = load_directory(config_root / "application")
    environment_path = config_root / "environments" / f"{environment}.json"
    environment_values = load_json_file(environment_path)
    values = deep_merge(base, environment_values)
    values = _apply_environment_overrides(values)
    validate_platform_config(values)

    return LoadedConfiguration(environment, root, config_root, values)

