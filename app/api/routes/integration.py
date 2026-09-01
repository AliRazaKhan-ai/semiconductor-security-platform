"""API routes for the complete integrated semiconductor pipeline."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)

from app.integration import IntegratedPipelineService
from app.integration.service import IntegrationError

bp = Blueprint(
    "integration",
    __name__,
    url_prefix="/integration",
)


def integration_service() -> IntegratedPipelineService:
    service = current_app.extensions.get(
        "semisecure.integrated_pipeline"
    )

    if not isinstance(
        service,
        IntegratedPipelineService,
    ):
        raise IntegrationError(
            "Integrated pipeline is unavailable"
        )

    return service


@bp.post("/run")
def run_pipeline():
    payload = request.get_json(
        silent=True,
    )

    if not isinstance(payload, dict):
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": "invalid_request",
                    "message": (
                        "JSON object is required"
                    ),
                },
            }
        ), 400

    source_file = str(
        payload.get("source_file") or ""
    ).strip()

    if not source_file:
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": "missing_source_file",
                    "message": (
                        "source_file is required"
                    ),
                },
            }
        ), 400

    try:
        result = integration_service().run_file(
            Path(source_file),
            force=bool(
                payload.get("force", False)
            ),
        )
    except (
        IntegrationError,
        FileNotFoundError,
    ) as exc:
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": (
                        "integration_failed"
                    ),
                    "message": str(exc),
                },
            }
        ), 422

    return jsonify(
        {
            "ok": True,
            "data": result,
        }
    ), 201


@bp.get("/runs")
def list_runs():
    limit = request.args.get(
        "limit",
        default=100,
        type=int,
    )

    limit = max(
        1,
        min(limit, 1000),
    )

    return jsonify(
        {
            "ok": True,
            "data": {
                "runs": integration_service().list_runs(
                    limit=limit
                )
            },
        }
    )


@bp.get("/runs/<identifier>")
def get_run(identifier: str):
    try:
        run = integration_service().get_run(
            identifier
        )
    except FileNotFoundError:
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": "not_found",
                    "message": (
                        "Integrated run was not found"
                    ),
                },
            }
        ), 404

    return jsonify(
        {
            "ok": True,
            "data": run,
        }
    )
