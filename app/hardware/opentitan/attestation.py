"""Verification of OpenTitan-style software attestation evidence."""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from filelock import FileLock

from app.hardware.common import (
    HardwareIntegrationError,
    atomic_write_json,
    canonical_json,
    load_json,
)
from app.hardware.opentitan.schemas import (
    OpenTitanEvidence,
    OpenTitanResult,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_NONCE_HEX = re.compile(r"^[0-9a-f]+$")
_ZERO_DIGEST = "0" * 64


class OpenTitanAttestationVerifier:
    def __init__(
        self,
        *,
        trusted_firmware_digests: set[str],
        verification_key: bytes,
        allowed_lifecycle_states: set[str],
        minimum_counter: int = 0,
        minimum_nonce_bytes: int = 16,
        maximum_attestation_age_seconds: int = 300,
        maximum_future_skew_seconds: int = 30,
        replay_state_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(verification_key) < 32:
            raise ValueError(
                "verification_key must be at least 32 bytes"
            )

        trusted = {
            value.lower()
            for value in trusted_firmware_digests
        }

        if not trusted:
            raise ValueError(
                "at least one trusted firmware digest is required"
            )

        if any(
            not _HEX64.fullmatch(value)
            or value == _ZERO_DIGEST
            for value in trusted
        ):
            raise ValueError(
                "trusted firmware digests must be non-zero SHA-256 values"
            )

        states = {
            value.upper()
            for value in allowed_lifecycle_states
        }

        if not states:
            raise ValueError(
                "at least one lifecycle state is required"
            )

        if minimum_counter < 0:
            raise ValueError(
                "minimum_counter cannot be negative"
            )

        if minimum_nonce_bytes < 16:
            raise ValueError(
                "minimum_nonce_bytes must be at least 16"
            )

        if maximum_attestation_age_seconds < 1:
            raise ValueError(
                "maximum_attestation_age_seconds must be positive"
            )

        if maximum_future_skew_seconds < 0:
            raise ValueError(
                "maximum_future_skew_seconds cannot be negative"
            )

        self.trusted_firmware_digests = trusted
        self.key = verification_key
        self.allowed_states = states
        self.minimum_counter = minimum_counter
        self.minimum_nonce_bytes = minimum_nonce_bytes
        self.maximum_attestation_age_seconds = (
            maximum_attestation_age_seconds
        )
        self.maximum_future_skew_seconds = (
            maximum_future_skew_seconds
        )
        self.replay_state_path = replay_state_path
        self.clock = clock or (
            lambda: datetime.now(UTC)
        )

        self._memory_counters: dict[str, int] = {}
        self._memory_lock = threading.Lock()

    @staticmethod
    def _signed(evidence: OpenTitanEvidence) -> bytes:
        payload = evidence.to_dict()
        payload.pop("signature")
        return canonical_json(payload)

    def _timestamp_reasons(
        self,
        evidence: OpenTitanEvidence,
    ) -> tuple[str, ...]:
        try:
            timestamp = datetime.fromisoformat(
                evidence.timestamp_utc.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError:
            return ("INVALID_TIMESTAMP",)

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() != timedelta(0)
        ):
            return ("TIMESTAMP_NOT_UTC",)

        now = self.clock()

        if now.tzinfo is None:
            raise HardwareIntegrationError(
                "opentitan",
                "OpenTitan verifier clock must be timezone-aware",
            )

        now = now.astimezone(UTC)
        timestamp = timestamp.astimezone(UTC)

        future_limit = now + timedelta(
            seconds=self.maximum_future_skew_seconds
        )

        if timestamp > future_limit:
            return ("ATTESTATION_FROM_FUTURE",)

        age = now - timestamp

        if age > timedelta(
            seconds=self.maximum_attestation_age_seconds
        ):
            return ("STALE_ATTESTATION",)

        return ()

    def _nonce_valid(
        self,
        nonce: str,
    ) -> bool:
        normalised = nonce.lower()

        if (
            len(normalised) % 2 != 0
            or not _NONCE_HEX.fullmatch(normalised)
        ):
            return False

        nonce_bytes = len(normalised) // 2

        return (
            self.minimum_nonce_bytes
            <= nonce_bytes
            <= 64
        )

    def _consume_memory_counter(
        self,
        device_id: str,
        counter: int,
    ) -> bool:
        with self._memory_lock:
            previous = self._memory_counters.get(
                device_id,
                -1,
            )

            if counter <= previous:
                return False

            self._memory_counters[
                device_id
            ] = counter

            return True

    def _consume_persistent_counter(
        self,
        evidence: OpenTitanEvidence,
        evidence_digest: str,
    ) -> bool:
        path = self.replay_state_path

        if path is None:
            return self._consume_memory_counter(
                evidence.device_id,
                evidence.monotonic_counter,
            )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock = FileLock(
            f"{path}.lock"
        )

        with lock:
            if path.exists():
                state = load_json(path)
            else:
                state = {
                    "version": "1.0",
                    "devices": {},
                }

            if state.get("version") != "1.0":
                raise HardwareIntegrationError(
                    "opentitan",
                    "Unsupported OpenTitan replay-state version",
                )

            devices = state.get("devices")

            if not isinstance(devices, dict):
                raise HardwareIntegrationError(
                    "opentitan",
                    "OpenTitan replay state is malformed",
                )

            record = devices.get(
                evidence.device_id
            )

            if (
                record is not None
                and not isinstance(record, dict)
            ):
                raise HardwareIntegrationError(
                    "opentitan",
                    "OpenTitan replay device state is malformed",
                )

            try:
                previous = (
                    int(
                        record.get(
                            "highest_counter",
                            -1,
                        )
                    )
                    if record is not None
                    else -1
                )
            except (TypeError, ValueError) as exc:
                raise HardwareIntegrationError(
                    "opentitan",
                    "OpenTitan replay counter is malformed",
                ) from exc

            if (
                evidence.monotonic_counter
                <= previous
            ):
                return False

            devices[evidence.device_id] = {
                "highest_counter": (
                    evidence.monotonic_counter
                ),
                "last_evidence_digest": (
                    evidence_digest
                ),
                "updated_at_utc": (
                    self.clock()
                    .astimezone(UTC)
                    .isoformat()
                ),
            }

            atomic_write_json(
                path,
                state,
                mode=0o600,
            )

            return True

    def verify(
        self,
        evidence: OpenTitanEvidence,
    ) -> OpenTitanResult:
        reasons: list[str] = []

        if not _DEVICE_ID.fullmatch(
            evidence.device_id
        ):
            reasons.append(
                "INVALID_DEVICE_ID"
            )

        if (
            evidence.lifecycle_state.upper()
            not in self.allowed_states
        ):
            reasons.append(
                "LIFECYCLE_STATE_NOT_ALLOWED"
            )

        digests = (
            (
                "rom_digest",
                evidence.rom_digest,
            ),
            (
                "firmware_digest",
                evidence.firmware_digest,
            ),
            (
                "otp_digest",
                evidence.otp_digest,
            ),
        )

        for name, value in digests:
            if not _HEX64.fullmatch(
                value.lower()
            ):
                reasons.append(
                    f"INVALID_{name.upper()}"
                )

        if (
            evidence.firmware_digest.lower()
            not in self.trusted_firmware_digests
        ):
            reasons.append(
                "UNTRUSTED_FIRMWARE"
            )

        if (
            evidence.monotonic_counter
            < self.minimum_counter
        ):
            reasons.append(
                "ROLLBACK_COUNTER"
            )

        if not self._nonce_valid(
            evidence.nonce
        ):
            reasons.append(
                "INVALID_ATTESTATION_NONCE"
            )

        if evidence.certificate_chain:
            reasons.append(
                "CERTIFICATE_CHAIN_UNVERIFIED"
            )

        reasons.extend(
            self._timestamp_reasons(
                evidence
            )
        )

        expected = hmac.new(
            self.key,
            self._signed(evidence),
            hashlib.sha256,
        ).hexdigest()

        signature = evidence.signature.lower()

        if (
            not _HEX64.fullmatch(signature)
            or not hmac.compare_digest(
                expected,
                signature,
            )
        ):
            reasons.append(
                "INVALID_ATTESTATION_SIGNATURE"
            )

        evidence_digest = hashlib.sha256(
            canonical_json(
                evidence.to_dict()
            )
        ).hexdigest()

        if not reasons:
            if not self._consume_persistent_counter(
                evidence,
                evidence_digest,
            ):
                reasons.append(
                    "ATTESTATION_REPLAY_OR_ROLLBACK"
                )

        return OpenTitanResult(
            not reasons,
            (
                "ATTESTED"
                if not reasons
                else "REJECTED"
            ),
            tuple(reasons),
            evidence_digest,
            evidence.lifecycle_state,
            evidence.firmware_digest,
            evidence.monotonic_counter,
        )
