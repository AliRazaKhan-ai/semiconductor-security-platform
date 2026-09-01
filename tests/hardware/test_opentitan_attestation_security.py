"""Security tests for OpenTitan-style software attestation."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.hardware.common import (
    HardwareIntegrationError,
    canonical_json,
)
from app.hardware.opentitan import OpenTitanAdapter
from app.hardware.opentitan.attestation import (
    OpenTitanAttestationVerifier,
)
from app.hardware.opentitan.schemas import OpenTitanEvidence

KEY = b"k" * 32
FIRMWARE_DIGEST = "1" * 64
NOW = datetime(
    2026,
    8,
    19,
    7,
    0,
    0,
    tzinfo=UTC,
)


def _sign(
    evidence: OpenTitanEvidence,
) -> OpenTitanEvidence:
    payload = evidence.to_dict()
    payload.pop("signature")

    signature = hmac.new(
        KEY,
        canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()

    return replace(
        evidence,
        signature=signature,
    )


def _evidence(
    *,
    counter: int = 7,
    nonce: str = "ab" * 16,
    timestamp: str | None = None,
    certificate_chain: tuple[str, ...] = (),
) -> OpenTitanEvidence:
    return _sign(
        OpenTitanEvidence(
            device_id="CHIP-OT-001",
            lifecycle_state="PROD",
            boot_stage="ROM_EXT",
            rom_digest="2" * 64,
            firmware_digest=FIRMWARE_DIGEST,
            otp_digest="3" * 64,
            monotonic_counter=counter,
            nonce=nonce,
            signature="",
            certificate_chain=certificate_chain,
            timestamp_utc=(
                timestamp
                or NOW.isoformat()
            ),
        )
    )


def _verifier(
    replay_state_path: Path | None = None,
) -> OpenTitanAttestationVerifier:
    return OpenTitanAttestationVerifier(
        trusted_firmware_digests={
            FIRMWARE_DIGEST,
        },
        verification_key=KEY,
        allowed_lifecycle_states={
            "PROD",
        },
        minimum_counter=0,
        minimum_nonce_bytes=16,
        maximum_attestation_age_seconds=300,
        maximum_future_skew_seconds=30,
        replay_state_path=replay_state_path,
        clock=lambda: NOW,
    )


def test_valid_fresh_attestation_passes() -> None:
    result = _verifier().verify(
        _evidence()
    )

    assert result.passed is True
    assert result.status == "ATTESTED"
    assert result.reasons == ()


def test_tampered_signed_field_is_rejected() -> None:
    evidence = _evidence()

    tampered = replace(
        evidence,
        firmware_digest="4" * 64,
    )

    result = _verifier().verify(
        tampered
    )

    assert result.passed is False
    assert (
        "INVALID_ATTESTATION_SIGNATURE"
        in result.reasons
    )


def test_weak_nonce_is_rejected() -> None:
    result = _verifier().verify(
        _evidence(
            nonce="aa",
        )
    )

    assert result.passed is False
    assert (
        "INVALID_ATTESTATION_NONCE"
        in result.reasons
    )


def test_stale_attestation_is_rejected() -> None:
    stale = (
        NOW
        - timedelta(seconds=301)
    ).isoformat()

    result = _verifier().verify(
        _evidence(
            timestamp=stale,
        )
    )

    assert result.passed is False
    assert (
        "STALE_ATTESTATION"
        in result.reasons
    )


def test_future_attestation_is_rejected() -> None:
    future = (
        NOW
        + timedelta(seconds=31)
    ).isoformat()

    result = _verifier().verify(
        _evidence(
            timestamp=future,
        )
    )

    assert result.passed is False
    assert (
        "ATTESTATION_FROM_FUTURE"
        in result.reasons
    )


def test_non_utc_timestamp_is_rejected() -> None:
    result = _verifier().verify(
        _evidence(
            timestamp=(
                "2026-08-19T11:00:00+04:00"
            ),
        )
    )

    assert result.passed is False
    assert (
        "TIMESTAMP_NOT_UTC"
        in result.reasons
    )


def test_invalid_signature_is_rejected() -> None:
    evidence = replace(
        _evidence(),
        signature="0" * 64,
    )

    result = _verifier().verify(
        evidence
    )

    assert result.passed is False
    assert (
        "INVALID_ATTESTATION_SIGNATURE"
        in result.reasons
    )


def test_unverified_certificate_chain_is_rejected() -> None:
    result = _verifier().verify(
        _evidence(
            certificate_chain=(
                "unverified-certificate",
            ),
        )
    )

    assert result.passed is False
    assert (
        "CERTIFICATE_CHAIN_UNVERIFIED"
        in result.reasons
    )


def test_replay_is_rejected_across_verifier_instances(
    tmp_path: Path,
) -> None:
    state_path = (
        tmp_path
        / "opentitan-replay.json"
    )

    evidence = _evidence()

    first = _verifier(
        state_path
    ).verify(
        evidence
    )

    second = _verifier(
        state_path
    ).verify(
        evidence
    )

    assert first.passed is True
    assert second.passed is False
    assert (
        "ATTESTATION_REPLAY_OR_ROLLBACK"
        in second.reasons
    )

    assert (
        state_path.stat().st_mode
        & 0o777
    ) == 0o600


def test_lower_counter_is_rejected_after_higher_counter(
    tmp_path: Path,
) -> None:
    state_path = (
        tmp_path
        / "opentitan-replay.json"
    )

    first = _verifier(
        state_path
    ).verify(
        _evidence(
            counter=8,
            nonce="ab" * 16,
        )
    )

    second = _verifier(
        state_path
    ).verify(
        _evidence(
            counter=7,
            nonce="cd" * 16,
        )
    )

    assert first.passed is True
    assert second.passed is False
    assert (
        "ATTESTATION_REPLAY_OR_ROLLBACK"
        in second.reasons
    )


def test_zero_firmware_trust_anchor_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="non-zero SHA-256",
    ):
        OpenTitanAttestationVerifier(
            trusted_firmware_digests={
                "0" * 64,
            },
            verification_key=KEY,
            allowed_lifecycle_states={
                "PROD",
            },
        )


def test_adapter_fails_closed_on_empty_firmware_trust(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_root = (
        tmp_path
        / "configs/hardware"
    )

    config_root.mkdir(
        parents=True,
    )

    config = {
        "version": "1.1",
        "allowed_lifecycle_states": [
            "PROD",
        ],
        "trusted_firmware_digests": [],
        "minimum_counter": 0,
        "minimum_nonce_bytes": 16,
        "maximum_attestation_age_seconds": 300,
        "maximum_future_skew_seconds": 30,
        "replay_state_path": (
            "data/hardware/"
            "opentitan-replay.json"
        ),
    }

    (
        config_root
        / "opentitan.json"
    ).write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "SEMISURE_OPENTITAN_VERIFICATION_KEY",
        "K" * 32,
    )

    with pytest.raises(
        HardwareIntegrationError,
        match=(
            "Invalid OpenTitan "
            "attestation configuration"
        ),
    ):
        OpenTitanAdapter.from_project(
            tmp_path
        )
