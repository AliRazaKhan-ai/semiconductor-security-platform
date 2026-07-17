"""Standard result contract for every Phase 3 pipeline stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


VALID_STAGE_STATUSES = {
    "PENDING",
    "RUNNING",
    "PASSED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
    "MANUAL_REVIEW",
    "INFRASTRUCTURE_ERROR",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class StageResult:
    stage: str
    status: str
    stop_pipeline: bool = False
    risk_score: float = 0.0
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)
    evidence_hashes: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    started_at_utc: str = field(default_factory=utc_now)
    completed_at_utc: str | None = None
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STAGE_STATUSES:
            raise ValueError(
                f"Unsupported stage status: {self.status}"
            )

        if not self.stage:
            raise ValueError("stage is required")

        if not 0.0 <= float(self.risk_score) <= 1.0:
            raise ValueError("risk_score must be between 0 and 1")

        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def complete(
        self,
        *,
        status: str | None = None,
        stop_pipeline: bool | None = None,
    ) -> "StageResult":
        if status is not None:
            if status not in VALID_STAGE_STATUSES:
                raise ValueError(
                    f"Unsupported stage status: {status}"
                )
            self.status = status

        if stop_pipeline is not None:
            self.stop_pipeline = stop_pipeline

        completed = datetime.now(UTC)
        started = datetime.fromisoformat(self.started_at_utc)

        self.completed_at_utc = completed.isoformat(
            timespec="milliseconds"
        )
        self.duration_ms = round(
            (completed - started).total_seconds() * 1000,
            3,
        )

        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
