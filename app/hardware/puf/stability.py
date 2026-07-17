"""Purpose: Implement reliability, Hamming distance, environmental drift, and noise-distance algorithms.
Directory: app/hardware/puf.
Dependencies: math, statistics, PUF configuration and schemas.
Connection: Enrollment selects stable bits; verifier evaluates noisy responses and clone likelihood.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.hardware.puf.config import PUFConfig
from app.hardware.puf.schemas import PUFEnvironment


def majority_vote(bit_samples: Sequence[str]) -> tuple[str, tuple[float, ...]]:
    if not bit_samples:
        raise ValueError("at least one bit sample is required")
    width = len(bit_samples[0])
    if width == 0 or any(len(sample) != width for sample in bit_samples):
        raise ValueError("all bit samples must have the same non-zero width")
    if any(any(bit not in "01" for bit in sample) for sample in bit_samples):
        raise ValueError("bit samples must be binary")

    voted: list[str] = []
    reliability: list[float] = []
    for index in range(width):
        ones = sum(sample[index] == "1" for sample in bit_samples)
        zeros = len(bit_samples) - ones
        voted.append("1" if ones > zeros else "0")
        reliability.append(max(ones, zeros) / len(bit_samples))
    return "".join(voted), tuple(reliability)


def reliability_mask(reliability: Sequence[float], minimum: float) -> str:
    if not 0.5 <= minimum <= 1.0:
        raise ValueError("minimum reliability must be between 0.5 and 1.0")
    return "".join("1" if value >= minimum else "0" for value in reliability)


def combine_masks(*masks: str) -> str:
    if not masks:
        raise ValueError("at least one mask is required")
    width = len(masks[0])
    if any(len(mask) != width for mask in masks):
        raise ValueError("all masks must have equal width")
    return "".join("1" if all(mask[index] == "1" for mask in masks) else "0" for index in range(width))


def masked_hamming_distance(reference: str, observed: str, mask: str) -> tuple[int, int, float]:
    if not (len(reference) == len(observed) == len(mask)):
        raise ValueError("reference, observed, and mask lengths must match")
    selected = [index for index, value in enumerate(mask) if value == "1"]
    if not selected:
        raise ValueError("reliability mask contains no stable bits")
    distance = sum(reference[index] != observed[index] for index in selected)
    return distance, len(selected), distance / len(selected)


def shannon_entropy(bits: str) -> float:
    if not bits:
        return 0.0
    ones = bits.count("1") / len(bits)
    zeros = 1.0 - ones
    entropy = 0.0
    for probability in (zeros, ones):
        if probability > 0:
            entropy -= probability * math.log2(probability)
    return entropy


def vector_mean(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    if not vectors:
        raise ValueError("at least one vector is required")
    width = len(vectors[0])
    if width == 0 or any(len(vector) != width for vector in vectors):
        raise ValueError("vectors must have equal non-zero width")
    return tuple(sum(vector[index] for vector in vectors) / len(vectors) for index in range(width))


def vector_scale(vectors: Sequence[Sequence[float]], floor: float = 1e-6) -> tuple[float, ...]:
    mean = vector_mean(vectors)
    if len(vectors) == 1:
        return tuple(max(abs(value) * 0.02, floor) for value in mean)
    width = len(mean)
    scales: list[float] = []
    for index in range(width):
        variance = sum((vector[index] - mean[index]) ** 2 for vector in vectors) / (len(vectors) - 1)
        scales.append(max(math.sqrt(variance), abs(mean[index]) * 0.005, floor))
    return tuple(scales)


def normalised_noise_distance(
    reference: Sequence[float],
    observed: Sequence[float],
    scale: Sequence[float],
) -> float:
    if not (len(reference) == len(observed) == len(scale)) or not reference:
        raise ValueError("noise vectors and scale must have equal non-zero width")
    squared = 0.0
    for expected, actual, sigma in zip(reference, observed, scale, strict=True):
        denominator = max(abs(sigma), 1e-9)
        squared += ((actual - expected) / denominator) ** 2
    return math.sqrt(squared / len(reference))


def environment_penalty(environment: PUFEnvironment, config: PUFConfig) -> float:
    temperature_span = max(
        config.environment.nominal_temperature_c - config.environment.minimum_temperature_c,
        config.environment.maximum_temperature_c - config.environment.nominal_temperature_c,
        1e-9,
    )
    voltage_span = max(
        config.environment.nominal_voltage_v - config.environment.minimum_voltage_v,
        config.environment.maximum_voltage_v - config.environment.nominal_voltage_v,
        1e-9,
    )
    temperature_component = abs(environment.temperature_c - config.environment.nominal_temperature_c) / temperature_span
    voltage_component = abs(environment.voltage_v - config.environment.nominal_voltage_v) / voltage_span
    aging_component = min(environment.age_hours / 100_000.0, 1.0)
    return math.sqrt((temperature_component**2 + voltage_component**2 + aging_component**2) / 3.0)


def within_supported_environment(environment: PUFEnvironment, config: PUFConfig) -> bool:
    return (
        config.environment.minimum_temperature_c <= environment.temperature_c <= config.environment.maximum_temperature_c
        and config.environment.minimum_voltage_v <= environment.voltage_v <= config.environment.maximum_voltage_v
    )


def clone_likelihood(hamming_ratio: float, maximum_accepted_ratio: float) -> float:
    if hamming_ratio <= maximum_accepted_ratio:
        return 0.0
    denominator = max(0.5 - maximum_accepted_ratio, 1e-9)
    return min(max((hamming_ratio - maximum_accepted_ratio) / denominator, 0.0), 1.0)
