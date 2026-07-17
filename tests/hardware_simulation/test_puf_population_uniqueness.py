"""Purpose: Validate PUF uniqueness across a population of simulated devices.
Directory: tests/hardware_simulation.
Dependencies: SemiSecure PUF simulator and distance utilities.
Connection: Prevents correlated device identities and weak inter-device separation.
"""

from __future__ import annotations

from itertools import combinations

from app.hardware.puf.crypto import derive_key
from app.hardware.puf.schemas import PUFEnvironment
from app.hardware.puf.simulator import ChallengeFactory, HybridPUFSimulator
from app.hardware.puf.stability import masked_hamming_distance

from tests.hardware_simulation.test_puf_simulator import _config


def test_population_mean_inter_device_distance_is_near_half() -> None:
    config = _config()
    issuer = derive_key(b"I" * 64, "issuer")
    challenge = ChallengeFactory(config, issuer).issue(100)

    devices = [
        HybridPUFSimulator(
            f"CHIP-{index}",
            bytes([index + 1]) * 64,
            config,
        )
        for index in range(8)
    ]

    responses = [
        device.respond(
            challenge,
            PUFEnvironment(),
            response_nonce_hex="09" * 16,
        ).response_bits
        for index, device in enumerate(devices)
    ]

    ratios: list[float] = []

    for first, second in combinations(responses, 2):
        _, _, ratio = masked_hamming_distance(
            first,
            second,
            "1" * config.total_response_bits,
        )
        ratios.append(ratio)

    mean_ratio = sum(ratios) / len(ratios)

    assert 0.40 <= mean_ratio <= 0.60
    assert min(ratios) >= 0.25
    assert max(ratios) <= 0.75
