"""Purpose: Load and strictly validate JSON configuration for the production PUF simulator.
Directory: app/hardware/puf.
Dependencies: dataclasses, pathlib, app.storage.config_store.
Connection: Adapter creates simulator, enrollment, verifier, repositories, and challenge policies from this model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.hardware.puf.crypto import canonical_json, sha256_hex
from app.hardware.puf.exceptions import PUFConfigurationError
from app.storage.config_store import load_json_file


def _number(value: Any, name: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PUFConfigurationError(f"{name} must be a number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise PUFConfigurationError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise PUFConfigurationError(f"{name} must be at most {maximum}")
    return result


def _integer(value: Any, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PUFConfigurationError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise PUFConfigurationError(f"{name} is outside the permitted range")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PUFConfigurationError(f"{name} must be a JSON object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    nominal_temperature_c: float
    nominal_voltage_v: float
    minimum_temperature_c: float
    maximum_temperature_c: float
    minimum_voltage_v: float
    maximum_voltage_v: float


@dataclass(frozen=True, slots=True)
class RingOscillatorConfig:
    oscillator_count: int
    response_bits: int
    nominal_frequency_hz: float
    process_sigma_ppm: float
    measurement_window_s: float
    voltage_exponent: float
    temperature_coefficient_ppm_per_c: float
    aging_coefficient_ppm_per_1000h: float
    counter_jitter_cycles: float


@dataclass(frozen=True, slots=True)
class DelayChainConfig:
    stage_count: int
    response_bits: int
    nominal_stage_delay_ps: float
    process_sigma_ps: float
    voltage_exponent: float
    temperature_coefficient_ppm_per_c: float
    aging_coefficient_ppm_per_1000h: float
    arbiter_jitter_ps: float


@dataclass(frozen=True, slots=True)
class NoiseConfig:
    correlated_noise_ppm: float
    white_noise_ppm: float
    flicker_noise_ppm: float
    delay_noise_ps: float
    signature_dimensions: int
    signature_run_sigma: float


@dataclass(frozen=True, slots=True)
class EnrollmentConfig:
    challenge_count: int
    response_samples: int
    minimum_bit_reliability: float
    minimum_stable_bit_ratio: float
    corners: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class AuthenticationConfig:
    response_samples: int
    challenge_ttl_seconds: int
    maximum_masked_hamming_ratio: float
    minimum_response_reliability: float
    maximum_noise_distance: float
    maximum_environment_penalty: float


@dataclass(frozen=True, slots=True)
class StorageConfig:
    enrollment_root: str
    challenge_ledger_path: str


@dataclass(frozen=True, slots=True)
class PUFConfig:
    version: str
    environment: EnvironmentConfig
    ring_oscillator: RingOscillatorConfig
    delay_chain: DelayChainConfig
    noise: NoiseConfig
    enrollment: EnrollmentConfig
    authentication: AuthenticationConfig
    storage: StorageConfig

    @property
    def total_response_bits(self) -> int:
        return self.ring_oscillator.response_bits + self.delay_chain.response_bits

    @property
    def fingerprint(self) -> str:
        return sha256_hex(canonical_json(asdict(self)))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PUFConfig":
        root = _mapping(raw.get("puf"), "puf")
        environment = _mapping(root.get("environment"), "puf.environment")
        ring = _mapping(root.get("ring_oscillator"), "puf.ring_oscillator")
        delay = _mapping(root.get("delay_chain"), "puf.delay_chain")
        noise = _mapping(root.get("noise"), "puf.noise")
        enrollment = _mapping(root.get("enrollment"), "puf.enrollment")
        authentication = _mapping(root.get("authentication"), "puf.authentication")
        storage = _mapping(root.get("storage"), "puf.storage")

        corners_value = enrollment.get("corners")
        if not isinstance(corners_value, list) or not corners_value:
            raise PUFConfigurationError("puf.enrollment.corners must be a non-empty array")
        corners: list[tuple[float, float]] = []
        for index, corner in enumerate(corners_value):
            corner_map = _mapping(corner, f"puf.enrollment.corners[{index}]")
            corners.append(
                (
                    _number(corner_map.get("temperature_c"), f"corner[{index}].temperature_c", minimum=-100, maximum=200),
                    _number(corner_map.get("voltage_v"), f"corner[{index}].voltage_v", minimum=0.1, maximum=5.0),
                )
            )

        result = cls(
            version=str(root.get("version", "1.0.0")),
            environment=EnvironmentConfig(
                nominal_temperature_c=_number(environment.get("nominal_temperature_c"), "nominal_temperature_c", minimum=-100, maximum=200),
                nominal_voltage_v=_number(environment.get("nominal_voltage_v"), "nominal_voltage_v", minimum=0.1, maximum=5.0),
                minimum_temperature_c=_number(environment.get("minimum_temperature_c"), "minimum_temperature_c", minimum=-100, maximum=200),
                maximum_temperature_c=_number(environment.get("maximum_temperature_c"), "maximum_temperature_c", minimum=-100, maximum=200),
                minimum_voltage_v=_number(environment.get("minimum_voltage_v"), "minimum_voltage_v", minimum=0.1, maximum=5.0),
                maximum_voltage_v=_number(environment.get("maximum_voltage_v"), "maximum_voltage_v", minimum=0.1, maximum=5.0),
            ),
            ring_oscillator=RingOscillatorConfig(
                oscillator_count=_integer(ring.get("oscillator_count"), "oscillator_count", minimum=8, maximum=4096),
                response_bits=_integer(ring.get("response_bits"), "ring response_bits", minimum=1, maximum=1024),
                nominal_frequency_hz=_number(ring.get("nominal_frequency_hz"), "nominal_frequency_hz", minimum=1_000),
                process_sigma_ppm=_number(ring.get("process_sigma_ppm"), "ring process_sigma_ppm", minimum=1),
                measurement_window_s=_number(ring.get("measurement_window_s"), "measurement_window_s", minimum=1e-9),
                voltage_exponent=_number(ring.get("voltage_exponent"), "ring voltage_exponent", minimum=0.01, maximum=10),
                temperature_coefficient_ppm_per_c=_number(ring.get("temperature_coefficient_ppm_per_c"), "ring temperature coefficient", minimum=-100_000, maximum=100_000),
                aging_coefficient_ppm_per_1000h=_number(ring.get("aging_coefficient_ppm_per_1000h"), "ring aging coefficient", minimum=0, maximum=100_000),
                counter_jitter_cycles=_number(ring.get("counter_jitter_cycles"), "counter_jitter_cycles", minimum=0),
            ),
            delay_chain=DelayChainConfig(
                stage_count=_integer(delay.get("stage_count"), "delay stage_count", minimum=8, maximum=2048),
                response_bits=_integer(delay.get("response_bits"), "delay response_bits", minimum=1, maximum=1024),
                nominal_stage_delay_ps=_number(delay.get("nominal_stage_delay_ps"), "nominal_stage_delay_ps", minimum=0.001),
                process_sigma_ps=_number(delay.get("process_sigma_ps"), "delay process_sigma_ps", minimum=0.0001),
                voltage_exponent=_number(delay.get("voltage_exponent"), "delay voltage_exponent", minimum=0.01, maximum=10),
                temperature_coefficient_ppm_per_c=_number(delay.get("temperature_coefficient_ppm_per_c"), "delay temperature coefficient", minimum=-100_000, maximum=100_000),
                aging_coefficient_ppm_per_1000h=_number(delay.get("aging_coefficient_ppm_per_1000h"), "delay aging coefficient", minimum=0, maximum=100_000),
                arbiter_jitter_ps=_number(delay.get("arbiter_jitter_ps"), "arbiter_jitter_ps", minimum=0),
            ),
            noise=NoiseConfig(
                correlated_noise_ppm=_number(noise.get("correlated_noise_ppm"), "correlated_noise_ppm", minimum=0),
                white_noise_ppm=_number(noise.get("white_noise_ppm"), "white_noise_ppm", minimum=0),
                flicker_noise_ppm=_number(noise.get("flicker_noise_ppm"), "flicker_noise_ppm", minimum=0),
                delay_noise_ps=_number(noise.get("delay_noise_ps"), "delay_noise_ps", minimum=0),
                signature_dimensions=_integer(noise.get("signature_dimensions"), "signature_dimensions", minimum=4, maximum=64),
                signature_run_sigma=_number(noise.get("signature_run_sigma"), "signature_run_sigma", minimum=0),
            ),
            enrollment=EnrollmentConfig(
                challenge_count=_integer(enrollment.get("challenge_count"), "challenge_count", minimum=4, maximum=4096),
                response_samples=_integer(enrollment.get("response_samples"), "enrollment response_samples", minimum=3, maximum=255),
                minimum_bit_reliability=_number(enrollment.get("minimum_bit_reliability"), "minimum_bit_reliability", minimum=0.5, maximum=1.0),
                minimum_stable_bit_ratio=_number(enrollment.get("minimum_stable_bit_ratio"), "minimum_stable_bit_ratio", minimum=0.1, maximum=1.0),
                corners=tuple(corners),
            ),
            authentication=AuthenticationConfig(
                response_samples=_integer(authentication.get("response_samples"), "authentication response_samples", minimum=3, maximum=255),
                challenge_ttl_seconds=_integer(authentication.get("challenge_ttl_seconds"), "challenge_ttl_seconds", minimum=1, maximum=86_400),
                maximum_masked_hamming_ratio=_number(authentication.get("maximum_masked_hamming_ratio"), "maximum_masked_hamming_ratio", minimum=0, maximum=0.49),
                minimum_response_reliability=_number(authentication.get("minimum_response_reliability"), "minimum_response_reliability", minimum=0.5, maximum=1.0),
                maximum_noise_distance=_number(authentication.get("maximum_noise_distance"), "maximum_noise_distance", minimum=0),
                maximum_environment_penalty=_number(authentication.get("maximum_environment_penalty"), "maximum_environment_penalty", minimum=0),
            ),
            storage=StorageConfig(
                enrollment_root=str(storage.get("enrollment_root", "data/puf/enrollments")),
                challenge_ledger_path=str(storage.get("challenge_ledger_path", "data/puf/challenge_ledger.jsonl")),
            ),
        )
        result._validate_relationships()
        return result

    def _validate_relationships(self) -> None:
        if self.environment.minimum_temperature_c >= self.environment.maximum_temperature_c:
            raise PUFConfigurationError("minimum temperature must be lower than maximum temperature")
        if self.environment.minimum_voltage_v >= self.environment.maximum_voltage_v:
            raise PUFConfigurationError("minimum voltage must be lower than maximum voltage")
        if not self.environment.minimum_temperature_c <= self.environment.nominal_temperature_c <= self.environment.maximum_temperature_c:
            raise PUFConfigurationError("nominal temperature must be inside the supported range")
        if not self.environment.minimum_voltage_v <= self.environment.nominal_voltage_v <= self.environment.maximum_voltage_v:
            raise PUFConfigurationError("nominal voltage must be inside the supported range")
        if self.ring_oscillator.response_bits * 2 > self.ring_oscillator.oscillator_count * (self.ring_oscillator.oscillator_count - 1):
            raise PUFConfigurationError("ring oscillator population is too small for the configured response")
        if self.enrollment.minimum_stable_bit_ratio * self.total_response_bits < 8:
            raise PUFConfigurationError("enrollment policy must retain at least eight stable response bits")
        for temperature_c, voltage_v in self.enrollment.corners:
            if not self.environment.minimum_temperature_c <= temperature_c <= self.environment.maximum_temperature_c:
                raise PUFConfigurationError("enrollment corner temperature is outside the supported range")
            if not self.environment.minimum_voltage_v <= voltage_v <= self.environment.maximum_voltage_v:
                raise PUFConfigurationError("enrollment corner voltage is outside the supported range")


def load_puf_config(path: Path) -> PUFConfig:
    return PUFConfig.from_dict(load_json_file(path))
