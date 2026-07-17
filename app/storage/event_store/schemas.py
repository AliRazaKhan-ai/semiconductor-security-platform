"""Purpose: Define the immutable JSON event envelope.
Directory: app/storage/event_store.
Dependencies: dataclasses, datetime, uuid.
Connection: Created by EventWriter and consumed by readers, indexes, snapshots, and SocketIO.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.constants import EVENT_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    scan_id: str
    chip_id: str
    sequence: int
    event_type: str
    pipeline_stage: str
    timestamp_utc: str
    correlation_id: str
    source_component: str
    component_version: str
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_hashes: dict[str, str] = field(default_factory=dict)
    previous_event_hash: str = ""
    event_hash: str = ""
    schema_version: str = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EventRecord":
        return cls(
            event_id=str(value["event_id"]),
            scan_id=str(value["scan_id"]),
            chip_id=str(value["chip_id"]),
            sequence=int(value["sequence"]),
            event_type=str(value["event_type"]),
            pipeline_stage=str(value["pipeline_stage"]),
            timestamp_utc=str(value["timestamp_utc"]),
            correlation_id=str(value["correlation_id"]),
            source_component=str(value["source_component"]),
            component_version=str(value["component_version"]),
            payload=dict(value.get("payload", {})),
            evidence_hashes={str(k): str(v) for k, v in dict(value.get("evidence_hashes", {})).items()},
            previous_event_hash=str(value.get("previous_event_hash", "")),
            event_hash=str(value.get("event_hash", "")),
            schema_version=str(value.get("schema_version", EVENT_SCHEMA_VERSION)),
        )

    @classmethod
    def new(
        cls,
        *,
        scan_id: str,
        chip_id: str,
        sequence: int,
        event_type: str,
        pipeline_stage: str,
        correlation_id: str,
        source_component: str,
        component_version: str,
        payload: dict[str, Any] | None = None,
        evidence_hashes: dict[str, str] | None = None,
        previous_event_hash: str = "",
    ) -> "EventRecord":
        return cls(
            event_id=str(uuid4()),
            scan_id=scan_id,
            chip_id=chip_id,
            sequence=sequence,
            event_type=event_type,
            pipeline_stage=pipeline_stage,
            timestamp_utc=datetime.now(UTC).isoformat(timespec="milliseconds"),
            correlation_id=correlation_id,
            source_component=source_component,
            component_version=component_version,
            payload=payload or {},
            evidence_hashes=evidence_hashes or {},
            previous_event_hash=previous_event_hash,
        )


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    path: str
    line_number: int
    message: str


@dataclass(frozen=True, slots=True)
class VerificationReport:
    valid: bool
    files_checked: int
    events_checked: int
    issues: tuple[VerificationIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "files_checked": self.files_checked,
            "events_checked": self.events_checked,
            "issues": [asdict(issue) for issue in self.issues],
        }

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

