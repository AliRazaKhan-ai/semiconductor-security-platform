"""Purpose: Report whether the Flask process can serve requests.
Directory: app/observability/health.
Dependencies: datetime.
Connection: Exposed at /health/live and used by process supervisors.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def liveness_payload() -> dict[str, Any]:
    return {
        "status": "alive",
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
    }

