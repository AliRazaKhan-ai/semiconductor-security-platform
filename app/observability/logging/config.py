"""Purpose: Configure console and rotating JSON file logging.
Directory: app/observability/logging.
Dependencies: logging, pathlib, app.observability.logging.structured.
Connection: Called before Flask creates its default logging handler.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any

from app.observability.logging.structured import JsonFormatter


def configure_logging(config: dict[str, Any], project_root: Path) -> None:
    level_name = str(config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    redacted_fields = {str(item).lower() for item in config.get("redacted_fields", [])}
    formatter = JsonFormatter(redacted_fields)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    if bool(config.get("console", True)):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        root_logger.addHandler(console)

    if bool(config.get("file", True)):
        file_path = Path(str(config.get("file_path", "runtime/logs/semisecure.jsonl")))
        if not file_path.is_absolute():
            file_path = project_root / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=int(config.get("max_bytes", 10_485_760)),
            backupCount=int(config.get("backup_count", 10)),
            encoding="utf-8",
        )
        rotating.setFormatter(formatter)
        rotating.setLevel(level)
        root_logger.addHandler(rotating)

    logging.captureWarnings(True)

