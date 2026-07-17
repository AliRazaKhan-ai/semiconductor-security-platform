"""Purpose: Hash audit records independently from operational scan events.
Directory: app/storage/audit.
Dependencies: hashlib, canonical JSON.
Connection: AuditWriter uses this to chain API and security operations.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.storage.event_store.hash_chain import canonical_json


def audit_hash(record: dict[str, Any]) -> str:
    content = dict(record)
    content["record_hash"] = ""
    return hashlib.sha256(canonical_json(content)).hexdigest()

