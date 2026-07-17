"""Purpose: Load, merge, and normalise JSON configuration files.
Directory: app/storage/config_store.
Dependencies: json, pathlib, app.exceptions.
Connection: Used by app.config_loader for base and environment configuration.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.exceptions import ConfigurationError
from app.types import JSONObject


def load_json_file(path: Path) -> JSONObject:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigurationError(
            "Required configuration file does not exist",
            {"path": str(path)},
        ) from exc
    except OSError as exc:
        raise ConfigurationError(
            "Configuration file could not be read",
            {"path": str(path), "reason": str(exc)},
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Configuration file contains invalid JSON",
            {
                "path": str(path),
                "line": exc.lineno,
                "column": exc.colno,
                "reason": exc.msg,
            },
        ) from exc

    if not isinstance(parsed, dict):
        raise ConfigurationError(
            "Configuration root must be a JSON object",
            {"path": str(path)},
        )
    return parsed


def deep_merge(base: JSONObject, override: JSONObject) -> JSONObject:
    merged: dict[str, Any] = deepcopy(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_directory(directory: Path) -> JSONObject:
    if not directory.exists() or not directory.is_dir():
        raise ConfigurationError(
            "Configuration directory does not exist",
            {"path": str(directory)},
        )

    merged: JSONObject = {}
    for path in sorted(directory.glob("*.json")):
        merged = deep_merge(merged, load_json_file(path))
    return merged

