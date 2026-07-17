"""Purpose: Apply browser and API hardening headers without authentication.
Directory: app/security.
Dependencies: Flask Response.
Connection: Registered as a global after-request hook by the application factory.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response


def register_security_headers(app: Flask, config: dict[str, Any]) -> None:
    headers = dict(config.get("headers", {}))

    @app.after_request
    def apply_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", str(headers.get("content_type_options", "nosniff")))
        response.headers.setdefault("X-Frame-Options", str(headers.get("frame_options", "DENY")))
        response.headers.setdefault("Referrer-Policy", str(headers.get("referrer_policy", "no-referrer")))
        response.headers.setdefault("Permissions-Policy", str(headers.get("permissions_policy", "camera=(), microphone=(), geolocation=()")))
        response.headers.setdefault("Content-Security-Policy", str(headers.get("content_security_policy", "default-src 'self'")))
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store" if response.is_json else "no-cache")
        return response

