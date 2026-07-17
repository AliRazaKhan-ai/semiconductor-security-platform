"""Purpose: Attach correlation IDs, timing, audit, and structured request logs.
Directory: app/api.
Dependencies: Flask request globals, time, logging.
Connection: Registered globally by app.factory before routes execute.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from flask import Flask, Response, g, request

from app.constants import CORRELATION_HEADER
from app.exceptions import RateLimitError
from app.storage.audit import AuditWriter

logger = logging.getLogger(__name__)


def _client_key() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",", maxsplit=1)[0].strip() or request.remote_addr or "unknown"


def register_request_context(
    app: Flask,
    *,
    rate_limiter: Any,
    audit_writer: AuditWriter,
    rate_limit_config: dict[str, Any],
) -> None:
    enabled = bool(rate_limit_config.get("enabled", True))
    scan_submission_limit = int(rate_limit_config.get("scan_submission_requests", 20))

    @app.before_request
    def begin_request() -> None:
        supplied = request.headers.get(CORRELATION_HEADER, "").strip()
        g.correlation_id = supplied[:128] if supplied else str(uuid4())
        g.request_started = time.perf_counter()
        if enabled:
            limit = scan_submission_limit if request.method == "POST" and request.path.endswith("/scans") else None
            rate_limiter.check(f"{_client_key()}:{request.method}:{request.path}", limit=limit)

    @app.after_request
    def end_request(response: Response) -> Response:
        duration_ms = round((time.perf_counter() - g.request_started) * 1000, 3)
        response.headers[CORRELATION_HEADER] = g.correlation_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        logger.info(
            "http_request",
            extra={
                "correlation_id": g.correlation_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "remote_address": _client_key(),
                "content_length": request.content_length,
            },
        )
        if request.method != "GET" or response.status_code >= 400:
            audit_writer.write(
                "http.request",
                g.correlation_id,
                {
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "remote_address": _client_key(),
                },
            )
        return response

