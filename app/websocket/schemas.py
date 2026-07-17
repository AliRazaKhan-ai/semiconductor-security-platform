"""Purpose: Define SocketIO message envelopes and subscription validation.
Directory: app/websocket.
Dependencies: dataclasses, datetime.
Connection: Publisher and namespace use identical event contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from app.exceptions import ValidationError
from app.storage.event_store.schemas import EventRecord


@dataclass(frozen=True, slots=True)
class SocketEvent:
    event_id: str
    event_type: str
    scan_id: str
    chip_id: str
    sequence: int
    timestamp_utc: str
    pipeline_stage: str
    payload: dict[str, Any]
    event_hash: str

    @classmethod
    def from_record(cls, record: EventRecord) -> "SocketEvent":
        return cls(
            event_id=record.event_id,
            event_type=record.event_type,
            scan_id=record.scan_id,
            chip_id=record.chip_id,
            sequence=record.sequence,
            timestamp_utc=record.timestamp_utc,
            pipeline_stage=record.pipeline_stage,
            payload=record.payload,
            event_hash=record.event_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def server_message(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "data": data,
    }


def validate_subscription(data: Any) -> tuple[str, str | None]:
    if not isinstance(data, dict):
        raise ValidationError("Socket subscription must be a JSON object")
    channel = str(data.get("channel", "")).strip().lower()
    if channel not in {"all", "system", "scan"}:
        raise ValidationError("Socket channel must be one of: all, system, scan")
    scan_id = data.get("scan_id")
    if channel == "scan":
        if not isinstance(scan_id, str) or not scan_id.strip():
            raise ValidationError("scan_id is required for scan subscriptions")
        return channel, scan_id.strip()
    return channel, None

