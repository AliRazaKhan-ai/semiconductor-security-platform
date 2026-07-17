"""Purpose: Canonicalise and hash events into a tamper-evident chain.
Directory: app/storage/event_store.
Dependencies: hashlib, json, EventRecord.
Connection: EventWriter creates hashes; EventReader and Recovery verify them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from app.storage.event_store.schemas import EventRecord


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def calculate_event_hash(event: EventRecord) -> str:
    content = event.to_dict()
    content["event_hash"] = ""
    return hashlib.sha256(canonical_json(content)).hexdigest()


def seal_event(event: EventRecord) -> EventRecord:
    return replace(event, event_hash=calculate_event_hash(event))


def verify_event(event: EventRecord, expected_previous_hash: str) -> tuple[bool, str]:
    if event.previous_event_hash != expected_previous_hash:
        return False, "previous event hash does not match"
    expected_hash = calculate_event_hash(event)
    if event.event_hash != expected_hash:
        return False, "event hash does not match canonical event content"
    return True, ""


def verify_chain(events: Iterable[EventRecord]) -> tuple[bool, str, int]:
    previous_hash = ""
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            return False, f"expected sequence {expected_sequence}, received {event.sequence}", expected_sequence
        valid, reason = verify_event(event, previous_hash)
        if not valid:
            return False, reason, expected_sequence
        previous_hash = event.event_hash
        expected_sequence += 1
    return True, "", expected_sequence - 1

