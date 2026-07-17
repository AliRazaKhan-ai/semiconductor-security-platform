"""Purpose: Return a chip's complete cross-scan lifecycle history.
Directory: app/api/routes.
Dependencies: Flask, EventStore.
Connection: Supports provenance views without SQL joins.
"""

from __future__ import annotations

from flask import Blueprint, request

from app.api.response import success
from app.exceptions import ValidationError
from app.extensions import event_store

bp = Blueprint("chip_history", __name__)


@bp.get("/chips/<chip_id>/history")
def get_chip_history(chip_id: str):
    raw_limit = request.args.get("limit", "500")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ValidationError("Query parameter 'limit' must be an integer") from exc
    if limit < 1 or limit > 5000:
        raise ValidationError("Query parameter 'limit' must be between 1 and 5000")
    events = event_store().chip_history(chip_id, limit)
    return success(events, meta={"chip_id": chip_id, "count": len(events), "limit": limit})

