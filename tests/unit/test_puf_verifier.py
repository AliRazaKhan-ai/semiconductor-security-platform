"""Unit tests for PUF enrollment, identity hashing, authentication, and anti-cloning."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.config import load_puf_config
from tests.puf_test_config import compact_puf_config
from app.hardware.puf.exceptions import PUFIntegrityError, PUFReplayError
from app.hardware.puf.schemas import PUFEnvironment


def _adapter(tmp_path: Path) -> PUFAdapter:
    return PUFAdapter(
        config=compact_puf_config(),
        master_secret=b"production-test-master-secret-000000000000000000000000",
        project_root=tmp_path,
    )


def test_enrollment_produces_signed_hashed_identity(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    profile = adapter.enroll_device("CHIP-IDENTITY-001")

    profile.validate_signature(adapter.profile_secret)
    assert len(profile.identity_hash) == 64
    assert profile.identity_hash != "0" * 64
    assert len(profile.templates) == adapter.config.enrollment.challenge_count
    assert all(template.stable_bit_count >= 8 for template in profile.templates)
    assert all(template.sealed_reference_hex for template in profile.templates)


def test_genuine_device_authenticates_across_supported_drift(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.enroll_device("CHIP-GENUINE-001")

    environments = (
        PUFEnvironment(temperature_c=-20.0, voltage_v=0.95),
        PUFEnvironment(temperature_c=85.0, voltage_v=1.05),
        PUFEnvironment(temperature_c=25.0, voltage_v=0.90),
        PUFEnvironment(temperature_c=25.0, voltage_v=1.10),
    )
    for environment in environments:
        challenge = adapter.issue_challenge("CHIP-GENUINE-001")
        response = adapter.simulate_response("CHIP-GENUINE-001", challenge, environment)
        result = adapter.authenticate("CHIP-GENUINE-001", challenge, response)
        assert result.accepted
        assert result.status == "AUTHENTICATED"
        assert result.hamming_ratio <= adapter.config.authentication.maximum_masked_hamming_ratio


def test_clone_with_independent_process_variation_is_rejected(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.enroll_device("TARGET-CHIP-001")
    challenge = adapter.issue_challenge("TARGET-CHIP-001")

    clone = adapter.simulator("COUNTERFEIT-CHIP-001")
    clone_response = clone.respond(
        challenge,
        PUFEnvironment(),
        sample_count=adapter.config.authentication.response_samples,
    )
    result = adapter.authenticate("TARGET-CHIP-001", challenge, clone_response)

    assert not result.accepted
    assert result.status == "REJECTED_POSSIBLE_CLONE"
    assert "RESPONSE_MISMATCH" in result.reasons
    assert result.clone_likelihood > 0.4


def test_one_time_challenge_replay_is_rejected(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.enroll_device("CHIP-REPLAY-001")
    challenge = adapter.issue_challenge("CHIP-REPLAY-001")
    response = adapter.simulate_response("CHIP-REPLAY-001", challenge)

    first = adapter.authenticate("CHIP-REPLAY-001", challenge, response)
    assert first.accepted
    with pytest.raises(PUFReplayError):
        adapter.authenticate("CHIP-REPLAY-001", challenge, response)


def test_tampered_profile_signature_is_rejected(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    profile = adapter.enroll_device("CHIP-TAMPER-001")
    tampered = replace(profile, identity_hash="f" * 64)

    with pytest.raises(PUFIntegrityError):
        tampered.validate_signature(adapter.profile_secret)


def test_response_from_unsupported_environment_fails_closed(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.enroll_device("CHIP-ENV-001")
    challenge = adapter.issue_challenge("CHIP-ENV-001")
    response = adapter.simulate_response(
        "CHIP-ENV-001",
        challenge,
        PUFEnvironment(temperature_c=150.0, voltage_v=1.30),
    )
    result = adapter.authenticate("CHIP-ENV-001", challenge, response)

    assert not result.accepted
    assert "UNSUPPORTED_ENVIRONMENT" in result.reasons
