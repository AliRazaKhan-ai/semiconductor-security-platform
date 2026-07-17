"""Purpose: Define immutable platform constants.
Directory: app.
Dependencies: Python standard library.
Connection: Shared by configuration, API, storage, and WebSocket modules.
"""

from __future__ import annotations

from enum import StrEnum

APP_NAME = "SemiSecure Platform"
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
SOCKET_NAMESPACE = "/events"
CORRELATION_HEADER = "X-Correlation-ID"
IDEMPOTENCY_HEADER = "Idempotency-Key"
DEFAULT_ENVIRONMENT = "development"
EVENT_SCHEMA_VERSION = "1.0"
MAX_IDENTIFIER_LENGTH = 128


class ScanStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class EventType(StrEnum):
    SCAN_ACCEPTED = "scan.accepted"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    RISK_UPDATED = "risk.updated"
    COMPLIANCE_COMPLETED = "compliance.completed"
    FABRIC_SUBMITTED = "fabric.submitted"
    FABRIC_COMMITTED = "fabric.committed"
    ETHEREUM_ANCHOR_SUBMITTED = "ethereum.anchor_submitted"
    ETHEREUM_ANCHOR_CONFIRMED = "ethereum.anchor_confirmed"
    DEPLOYMENT_APPROVED = "deployment.approved"
    DEPLOYMENT_REJECTED = "deployment.rejected"
    CHIP_QUARANTINED = "chip.quarantined"
    SYSTEM_HEALTH_CHANGED = "system.health_changed"

