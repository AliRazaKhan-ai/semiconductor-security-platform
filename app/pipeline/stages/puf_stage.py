"""Purpose: Execute PUF authentication as the first fail-closed security pipeline stage.
Directory: app/pipeline/stages.
Dependencies: PUFAdapter, JSON EventStore, SocketPublisher protocol, event constants.
Connection: Terminal-supplied challenge/response evidence is verified before OpenTitan and later stages run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.constants import EventType
from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.exceptions import PUFError
from app.hardware.puf.schemas import AuthenticationResult, PUFChallenge, PUFResponse
from app.storage.event_store import EventStore
from app.storage.event_store.schemas import EventRecord


class EventPublisher(Protocol):
    def publish_record(self, record: EventRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class PUFStageOutcome:
    passed: bool
    status: str
    authentication: dict[str, Any]
    failure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "authentication": self.authentication,
            "failure": self.failure,
        }


class PUFStage:
    name = "PUF_AUTHENTICATION"
    component = "puf-stage"

    def __init__(
        self,
        *,
        adapter: PUFAdapter,
        event_store: EventStore,
        publisher: EventPublisher | None = None,
        component_version: str = "1.0.0",
    ) -> None:
        self.adapter = adapter
        self.event_store = event_store
        self.publisher = publisher
        self.component_version = component_version

    def execute(
        self,
        *,
        scan_id: str,
        chip_id: str,
        correlation_id: str,
        evidence: dict[str, Any],
    ) -> PUFStageOutcome:
        self._persist(
            scan_id=scan_id,
            chip_id=chip_id,
            correlation_id=correlation_id,
            event_type=EventType.STAGE_STARTED,
            payload={"status": "PROCESSING", "stage": self.name},
        )
        try:
            puf_evidence = evidence.get("puf")
            if not isinstance(puf_evidence, dict):
                raise ValueError("terminal evidence must contain a puf JSON object")
            challenge_value = puf_evidence.get("challenge")
            response_value = puf_evidence.get("response")
            if not isinstance(challenge_value, dict) or not isinstance(response_value, dict):
                raise ValueError("puf evidence requires challenge and response JSON objects")
            challenge = PUFChallenge.from_dict(challenge_value)
            response = PUFResponse.from_dict(response_value)
            result: AuthenticationResult = self.adapter.authenticate(
                chip_id,
                challenge,
                response,
            )
            event_type = EventType.STAGE_COMPLETED if result.accepted else EventType.STAGE_FAILED
            outcome = PUFStageOutcome(
                passed=result.accepted,
                status=result.status,
                authentication=result.to_dict(),
                failure=None if result.accepted else {
                    "code": "puf_authentication_rejected",
                    "reasons": list(result.reasons),
                },
            )
            self._persist(
                scan_id=scan_id,
                chip_id=chip_id,
                correlation_id=correlation_id,
                event_type=event_type,
                payload={
                    "status": "PASSED" if result.accepted else "FAILED",
                    "stage": self.name,
                    "result": outcome.to_dict(),
                    "stop_pipeline": not result.accepted,
                },
                evidence_hashes={
                    "puf_challenge": challenge.challenge_digest,
                    "puf_response": response.response_digest,
                    "puf_identity": result.identity_hash,
                },
            )
            return outcome
        except (PUFError, ValueError, KeyError, TypeError) as exc:
            failure = {
                "code": getattr(exc, "code", "puf_stage_validation_error"),
                "message": str(exc),
                "error_type": type(exc).__name__,
            }
            outcome = PUFStageOutcome(
                passed=False,
                status="FAILED_CLOSED",
                authentication={},
                failure=failure,
            )
            self._persist(
                scan_id=scan_id,
                chip_id=chip_id,
                correlation_id=correlation_id,
                event_type=EventType.STAGE_FAILED,
                payload={
                    "status": "FAILED",
                    "stage": self.name,
                    "result": outcome.to_dict(),
                    "stop_pipeline": True,
                },
            )
            return outcome

    def _persist(
        self,
        *,
        scan_id: str,
        chip_id: str,
        correlation_id: str,
        event_type: str,
        payload: dict[str, Any],
        evidence_hashes: dict[str, str] | None = None,
    ) -> EventRecord:
        record = self.event_store.append(
            scan_id=scan_id,
            chip_id=chip_id,
            event_type=event_type,
            pipeline_stage=self.name,
            correlation_id=correlation_id,
            source_component=self.component,
            component_version=self.component_version,
            payload=payload,
            evidence_hashes=evidence_hashes,
        )
        if self.publisher is not None:
            self.publisher.publish_record(record)
        return record
