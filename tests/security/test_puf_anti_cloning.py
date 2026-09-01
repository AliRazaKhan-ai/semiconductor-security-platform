"""Security tests for PUF challenge integrity, replay resistance, and clone detection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.config import load_puf_config
from app.hardware.puf.exceptions import PUFIntegrityError, PUFReplayError
from tests.puf_test_config import compact_puf_config


def _adapter(tmp_path: Path) -> PUFAdapter:
    return PUFAdapter(
        config=compact_puf_config(),
        master_secret=b"security-master-secret-00000000000000000000000000000",
        project_root=tmp_path,
    )


def test_challenge_tampering_invalidates_issuer_tag(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.enroll_device("CHIP-SEC-001")
    challenge = adapter.issue_challenge("CHIP-SEC-001")
    first_pair = challenge.ro_pairs[0]
    tampered_pairs = ((first_pair[1], first_pair[0]),) + challenge.ro_pairs[1:]
    tampered = replace(challenge, ro_pairs=tampered_pairs)

    with pytest.raises(PUFIntegrityError):
        tampered.validate(adapter.issuer_secret)


def test_failed_clone_attempt_consumes_challenge(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    target = "CHIP-SEC-002"
    adapter.enroll_device(target)
    challenge = adapter.issue_challenge(target)
    clone_response = adapter.simulator("CLONED-SEC-002").respond(
        challenge,
        sample_count=adapter.config.authentication.response_samples,
    )

    first = adapter.authenticate(target, challenge, clone_response)
    assert not first.accepted
    with pytest.raises(PUFReplayError):
        adapter.authenticate(target, challenge, clone_response)


def test_reference_response_is_not_stored_in_clear_text(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    profile = adapter.enroll_device("CHIP-SEC-003")
    profile_path = tmp_path / adapter.config.storage.enrollment_root / "CHIP-SEC-003.json"
    stored = profile_path.read_text(encoding="utf-8")

    challenge = profile.templates[0].challenge.reissue(
        adapter.issuer_secret,
        adapter.config.authentication.challenge_ttl_seconds,
    )
    clear_response = adapter.simulator("CHIP-SEC-003").respond(
        challenge,
        sample_count=adapter.config.authentication.response_samples,
        response_nonce_hex="aa" * 16,
    ).response_bits

    assert clear_response not in stored
    assert "sealed_reference_hex" in stored
    assert "profile_signature" in stored
