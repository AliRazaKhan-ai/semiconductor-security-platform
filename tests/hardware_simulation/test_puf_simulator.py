"""Production tests for hybrid Ring-Oscillator and Delay-Chain PUF behaviour."""

from __future__ import annotations

from pathlib import Path

from app.hardware.puf.config import load_puf_config
from app.hardware.puf.crypto import derive_key
from app.hardware.puf.schemas import PUFEnvironment
from app.hardware.puf.simulator import ChallengeFactory, HybridPUFSimulator
from app.hardware.puf.stability import masked_hamming_distance
from tests.puf_test_config import compact_puf_config


def _config():
    return compact_puf_config()


def test_same_device_is_stable_under_nominal_noise() -> None:
    config = _config()
    issuer = derive_key(b"I" * 64, "issuer")
    factory = ChallengeFactory(config, issuer)
    challenge = factory.issue(1)
    device = HybridPUFSimulator("CHIP-A", b"A" * 64, config)

    first = device.respond(challenge, PUFEnvironment(), response_nonce_hex="01" * 16)
    second = device.respond(challenge, PUFEnvironment(), response_nonce_hex="02" * 16)
    mask = "1" * len(first.response_bits)
    distance, width, ratio = masked_hamming_distance(first.response_bits, second.response_bits, mask)

    assert width == config.total_response_bits
    assert distance <= 8
    assert ratio <= 0.09
    assert first.overall_reliability >= 0.95
    assert second.overall_reliability >= 0.95


def test_different_physical_devices_have_high_inter_device_distance() -> None:
    config = _config()
    issuer = derive_key(b"I" * 64, "issuer")
    challenge = ChallengeFactory(config, issuer).issue(2)
    first_device = HybridPUFSimulator("CHIP-A", b"A" * 64, config)
    second_device = HybridPUFSimulator("CHIP-B", b"B" * 64, config)

    first = first_device.respond(challenge, PUFEnvironment(), response_nonce_hex="03" * 16)
    second = second_device.respond(challenge, PUFEnvironment(), response_nonce_hex="04" * 16)
    _, _, ratio = masked_hamming_distance(
        first.response_bits,
        second.response_bits,
        "1" * config.total_response_bits,
    )

    assert 0.30 <= ratio <= 0.70
    assert first.noise_signature.signature_hash != second.noise_signature.signature_hash


def test_enrollment_operating_corners_preserve_response() -> None:
    config = _config()
    issuer = derive_key(b"I" * 64, "issuer")
    challenge = ChallengeFactory(config, issuer).issue(3)
    device = HybridPUFSimulator("CHIP-C", b"C" * 64, config)
    nominal = device.respond(challenge, PUFEnvironment(), response_nonce_hex="05" * 16)

    for index, (temperature_c, voltage_v) in enumerate(config.enrollment.corners):
        corner = device.respond(
            challenge,
            PUFEnvironment(temperature_c=temperature_c, voltage_v=voltage_v),
            response_nonce_hex=f"{index + 6:02x}" * 16,
        )
        _, _, ratio = masked_hamming_distance(
            nominal.response_bits,
            corner.response_bits,
            "1" * config.total_response_bits,
        )
        assert ratio <= 0.18


def test_challenge_contains_expected_hybrid_stimulus() -> None:
    config = _config()
    issuer = derive_key(b"I" * 64, "issuer")
    challenge = ChallengeFactory(config, issuer).issue(4)

    challenge.validate(issuer)
    assert len(challenge.ro_pairs) == config.ring_oscillator.response_bits
    assert len(set(challenge.ro_pairs)) == len(challenge.ro_pairs)
    assert len(challenge.delay_challenges) == config.delay_chain.response_bits
    assert len(set(challenge.delay_challenges)) == len(challenge.delay_challenges)
    assert all(len(pattern) == config.delay_chain.stage_count for pattern in challenge.delay_challenges)
