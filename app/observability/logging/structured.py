"""Purpose: Produce one-line JSON logs with operational context.
Directory: app/observability/logging.
Dependencies: logging, json, datetime, redaction.
Connection: Installed on root and Flask loggers by configure_logging.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from app.observability.logging.redaction import redact

_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def __init__(self, redacted_fields: set[str] | None = None) -> None:
        super().__init__()
        self.redacted_fields = {field.lower() for field in (redacted_fields or set())}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.threadName,
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        return json.dumps(redact(payload, self.redacted_fields), separators=(",", ":"), default=str)

