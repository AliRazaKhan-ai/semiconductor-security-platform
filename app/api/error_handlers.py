"""Purpose: Convert platform and framework exceptions into stable REST errors.
Directory: app/api.
Dependencies: Flask, Werkzeug, app.exceptions.
Connection: Registered on the application so invalid URLs and API failures are consistent.
"""

from __future__ import annotations

import logging

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from app.api.response import failure
from app.exceptions import PlatformError

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(PlatformError)
    def handle_platform_error(error: PlatformError):
        if error.status_code >= 500:
            logger.exception(
                "platform_error",
                exc_info=error,
                extra={"error_code": error.code, "details": error.details},
            )
        else:
            logger.warning(
                "platform_request_error",
                extra={"error_code": error.code, "details": error.details},
            )
        response, status = failure(
            code=error.code,
            message=error.message,
            status=error.status_code,
            details=error.details,
        )
        if error.status_code == 429:
            retry_after = error.details.get("retry_after_seconds")
            if retry_after is not None:
                response.headers["Retry-After"] = str(retry_after)
        return response, status

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return failure(
            code=error.name.lower().replace(" ", "_"),
            message=error.description,
            status=error.code or 500,
            details={"path": request.path},
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("unhandled_exception", exc_info=error)
        return failure(
            code="internal_server_error",
            message="The request could not be completed",
            status=500,
        )

