"""Purpose: Standardise successful and failed REST response envelopes.
Directory: app/api.
Dependencies: Flask jsonify and request context.
Connection: Used by all API routes and error handlers.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, jsonify


def success(data: Any, *, status: int = 200, meta: dict[str, Any] | None = None) -> tuple[Response, int]:
    payload: dict[str, Any] = {
        "ok": True,
        "data": data,
        "correlation_id": getattr(g, "correlation_id", None),
    }
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def failure(
    *,
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    return (
        jsonify(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                },
                "correlation_id": getattr(g, "correlation_id", None),
            }
        ),
        status,
    )

