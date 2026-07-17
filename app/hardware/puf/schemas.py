"""Purpose: Define immutable JSON-serialisable contracts for PUF challenges, responses, enrollment, and authentication.
Directory: app/hardware/puf.
Dependencies: dataclasses, datetime, hmac, app.hardware.puf.crypto.
Connection: Shared by simulator, verifier, repositories, terminal CLI, and pipeline stage.
"""

from __future__ import annotations

import hmac
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.hardware.puf.crypto import canonical_json, hmac_hex, sha256_hex
from app.hardware.puf.exceptions import PUFIntegrityError


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return instant.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PUFEnvironment:
    temperature_c: float = 25.0
    voltage_v: float = 1.0
    age_hours: float = 0.0

    def __post_init__(self) -> None:
        if not -100.0 <= self.temperature_c <= 200.0:
            raise ValueError("temperature must be between -100 C and 200 C")
        if not 0.1 <= self.voltage_v <= 5.0:
            raise ValueError("voltage must be between 0.1 V and 5.0 V")
        if self.age_hours < 0:
            raise ValueError("age_hours cannot be negative")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PUFEnvironment":
        return cls(
            temperature_c=float(value.get("temperature_c", 25.0)),
            voltage_v=float(value.get("voltage_v", 1.0)),
            age_hours=float(value.get("age_hours", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class PUFChallenge:
    challenge_id: str
    sequence: int
    nonce_hex: str
    ro_pairs: tuple[tuple[int, int], ...]
    delay_challenges: tuple[str, ...]
    issued_at_utc: str
    expires_at_utc: str
    stimulus_digest: str
    challenge_digest: str
    issuer_tag: str

    @staticmethod
    def _stimulus_payload(
        nonce_hex: str,
        ro_pairs: tuple[tuple[int, int], ...],
        delay_challenges: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "nonce_hex": nonce_hex,
            "ro_pairs": [list(pair) for pair in ro_pairs],
            "delay_challenges": list(delay_challenges),
        }

    @staticmethod
    def _challenge_payload(
        challenge_id: str,
        sequence: int,
        issued_at_utc: str,
        expires_at_utc: str,
        stimulus_digest: str,
    ) -> dict[str, Any]:
        return {
            "challenge_id": challenge_id,
            "sequence": sequence,
            "issued_at_utc": issued_at_utc,
            "expires_at_utc": expires_at_utc,
            "stimulus_digest": stimulus_digest,
        }

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        nonce_hex: str,
        ro_pairs: tuple[tuple[int, int], ...],
        delay_challenges: tuple[str, ...],
        issuer_secret: bytes,
        ttl_seconds: int,
        challenge_id: str | None = None,
        now: datetime | None = None,
    ) -> "PUFChallenge":
        current = (now or utc_now()).astimezone(UTC)
        issued = current.isoformat(timespec="milliseconds")
        expires = (current + timedelta(seconds=ttl_seconds)).isoformat(timespec="milliseconds")
        identifier = challenge_id or str(uuid4())
        stimulus_digest = sha256_hex(canonical_json(cls._stimulus_payload(nonce_hex, ro_pairs, delay_challenges)))
        challenge_payload = cls._challenge_payload(identifier, sequence, issued, expires, stimulus_digest)
        challenge_digest = sha256_hex(canonical_json(challenge_payload))
        issuer_tag = hmac_hex(issuer_secret, b"puf-challenge", challenge_digest)
        return cls(
            challenge_id=identifier,
            sequence=sequence,
            nonce_hex=nonce_hex,
            ro_pairs=ro_pairs,
            delay_challenges=delay_challenges,
            issued_at_utc=issued,
            expires_at_utc=expires,
            stimulus_digest=stimulus_digest,
            challenge_digest=challenge_digest,
            issuer_tag=issuer_tag,
        )

    def reissue(self, issuer_secret: bytes, ttl_seconds: int, now: datetime | None = None) -> "PUFChallenge":
        return self.create(
            sequence=self.sequence,
            nonce_hex=self.nonce_hex,
            ro_pairs=self.ro_pairs,
            delay_challenges=self.delay_challenges,
            issuer_secret=issuer_secret,
            ttl_seconds=ttl_seconds,
            challenge_id=self.challenge_id,
            now=now,
        )

    def validate(self, issuer_secret: bytes, *, now: datetime | None = None, allow_expired: bool = False) -> None:
        expected_stimulus = sha256_hex(canonical_json(self._stimulus_payload(self.nonce_hex, self.ro_pairs, self.delay_challenges)))
        if not hmac.compare_digest(expected_stimulus, self.stimulus_digest):
            raise PUFIntegrityError("PUF challenge stimulus digest is invalid")
        payload = self._challenge_payload(
            self.challenge_id,
            self.sequence,
            self.issued_at_utc,
            self.expires_at_utc,
            self.stimulus_digest,
        )
        expected_digest = sha256_hex(canonical_json(payload))
        if not hmac.compare_digest(expected_digest, self.challenge_digest):
            raise PUFIntegrityError("PUF challenge digest is invalid")
        expected_tag = hmac_hex(issuer_secret, b"puf-challenge", self.challenge_digest)
        if not hmac.compare_digest(expected_tag, self.issuer_tag):
            raise PUFIntegrityError("PUF challenge issuer tag is invalid")
        issued = parse_utc(self.issued_at_utc)
        expires = parse_utc(self.expires_at_utc)
        current = (now or utc_now()).astimezone(UTC)
        if expires <= issued:
            raise PUFIntegrityError("PUF challenge expiry precedes issuance")
        if not allow_expired and current > expires:
            raise PUFIntegrityError("PUF challenge has expired")
        if issued > current + timedelta(seconds=5):
            raise PUFIntegrityError("PUF challenge issuance time is in the future")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["ro_pairs"] = [list(pair) for pair in self.ro_pairs]
        value["delay_challenges"] = list(self.delay_challenges)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PUFChallenge":
        return cls(
            challenge_id=str(value["challenge_id"]),
            sequence=int(value["sequence"]),
            nonce_hex=str(value["nonce_hex"]),
            ro_pairs=tuple((int(pair[0]), int(pair[1])) for pair in value["ro_pairs"]),
            delay_challenges=tuple(str(item) for item in value["delay_challenges"]),
            issued_at_utc=str(value["issued_at_utc"]),
            expires_at_utc=str(value["expires_at_utc"]),
            stimulus_digest=str(value["stimulus_digest"]),
            challenge_digest=str(value["challenge_digest"]),
            issuer_tag=str(value["issuer_tag"]),
        )


@dataclass(frozen=True, slots=True)
class NoiseSignature:
    components: tuple[float, ...]
    signature_hash: str

    @classmethod
    def create(cls, components: tuple[float, ...]) -> "NoiseSignature":
        quantised = [round(value, 8) for value in components]
        return cls(components=components, signature_hash=sha256_hex(canonical_json(quantised)))

    def to_dict(self) -> dict[str, Any]:
        return {"components": list(self.components), "signature_hash": self.signature_hash}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NoiseSignature":
        instance = cls(
            components=tuple(float(item) for item in value["components"]),
            signature_hash=str(value["signature_hash"]),
        )
        expected = cls.create(instance.components).signature_hash
        if not hmac.compare_digest(expected, instance.signature_hash):
            raise PUFIntegrityError("Noise signature hash is invalid")
        return instance


@dataclass(frozen=True, slots=True)
class PUFResponse:
    challenge_id: str
    challenge_digest: str
    stimulus_digest: str
    response_nonce_hex: str
    ro_bits: str
    delay_bits: str
    response_bits: str
    bit_reliability: tuple[float, ...]
    bit_margins: tuple[float, ...]
    overall_reliability: float
    sample_count: int
    environment: PUFEnvironment
    noise_signature: NoiseSignature
    generated_at_utc: str
    response_digest: str = ""

    def __post_init__(self) -> None:
        if self.response_bits != self.ro_bits + self.delay_bits:
            raise ValueError("response_bits must equal ro_bits followed by delay_bits")
        if any(bit not in "01" for bit in self.response_bits):
            raise ValueError("PUF response contains a non-binary value")
        if len(self.bit_reliability) != len(self.response_bits):
            raise ValueError("bit reliability length does not match response length")
        if len(self.bit_margins) != len(self.response_bits):
            raise ValueError("bit margin length does not match response length")
        if self.sample_count < 1:
            raise ValueError("sample_count must be positive")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "challenge_digest": self.challenge_digest,
            "stimulus_digest": self.stimulus_digest,
            "response_nonce_hex": self.response_nonce_hex,
            "ro_bits": self.ro_bits,
            "delay_bits": self.delay_bits,
            "response_bits": self.response_bits,
            "bit_reliability": list(self.bit_reliability),
            "bit_margins": list(self.bit_margins),
            "overall_reliability": self.overall_reliability,
            "sample_count": self.sample_count,
            "environment": self.environment.to_dict(),
            "noise_signature": self.noise_signature.to_dict(),
            "generated_at_utc": self.generated_at_utc,
        }

    def seal(self) -> "PUFResponse":
        return replace(self, response_digest=sha256_hex(canonical_json(self.unsigned_dict())))

    def validate(self) -> None:
        expected = sha256_hex(canonical_json(self.unsigned_dict()))
        if not hmac.compare_digest(expected, self.response_digest):
            raise PUFIntegrityError("PUF response digest is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "response_digest": self.response_digest}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PUFResponse":
        response = cls(
            challenge_id=str(value["challenge_id"]),
            challenge_digest=str(value["challenge_digest"]),
            stimulus_digest=str(value["stimulus_digest"]),
            response_nonce_hex=str(value["response_nonce_hex"]),
            ro_bits=str(value["ro_bits"]),
            delay_bits=str(value["delay_bits"]),
            response_bits=str(value["response_bits"]),
            bit_reliability=tuple(float(item) for item in value["bit_reliability"]),
            bit_margins=tuple(float(item) for item in value["bit_margins"]),
            overall_reliability=float(value["overall_reliability"]),
            sample_count=int(value["sample_count"]),
            environment=PUFEnvironment.from_dict(dict(value["environment"])),
            noise_signature=NoiseSignature.from_dict(dict(value["noise_signature"])),
            generated_at_utc=str(value["generated_at_utc"]),
            response_digest=str(value["response_digest"]),
        )
        response.validate()
        return response


@dataclass(frozen=True, slots=True)
class ChallengeTemplate:
    challenge: PUFChallenge
    sealed_reference_hex: str
    seal_tag_hex: str
    reliability_mask: str
    stable_bit_count: int
    minimum_reliability: float
    maximum_hamming_ratio: float
    reference_noise_vector: tuple[float, ...]
    noise_scale_vector: tuple[float, ...]
    response_commitment: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["challenge"] = self.challenge.to_dict()
        value["reference_noise_vector"] = list(self.reference_noise_vector)
        value["noise_scale_vector"] = list(self.noise_scale_vector)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ChallengeTemplate":
        return cls(
            challenge=PUFChallenge.from_dict(dict(value["challenge"])),
            sealed_reference_hex=str(value["sealed_reference_hex"]),
            seal_tag_hex=str(value["seal_tag_hex"]),
            reliability_mask=str(value["reliability_mask"]),
            stable_bit_count=int(value["stable_bit_count"]),
            minimum_reliability=float(value["minimum_reliability"]),
            maximum_hamming_ratio=float(value["maximum_hamming_ratio"]),
            reference_noise_vector=tuple(float(item) for item in value["reference_noise_vector"]),
            noise_scale_vector=tuple(float(item) for item in value["noise_scale_vector"]),
            response_commitment=str(value["response_commitment"]),
        )


@dataclass(frozen=True, slots=True)
class EnrollmentProfile:
    device_id: str
    identity_hash: str
    config_fingerprint: str
    enrolled_at_utc: str
    templates: tuple[ChallengeTemplate, ...]
    profile_version: str = "1.0"
    profile_signature: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "identity_hash": self.identity_hash,
            "config_fingerprint": self.config_fingerprint,
            "enrolled_at_utc": self.enrolled_at_utc,
            "templates": [template.to_dict() for template in self.templates],
            "profile_version": self.profile_version,
        }

    def sign(self, profile_secret: bytes) -> "EnrollmentProfile":
        signature = hmac_hex(profile_secret, b"puf-enrollment-profile", canonical_json(self.unsigned_dict()))
        return replace(self, profile_signature=signature)

    def validate_signature(self, profile_secret: bytes) -> None:
        expected = hmac_hex(profile_secret, b"puf-enrollment-profile", canonical_json(self.unsigned_dict()))
        if not hmac.compare_digest(expected, self.profile_signature):
            raise PUFIntegrityError("PUF enrollment profile signature is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "profile_signature": self.profile_signature}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EnrollmentProfile":
        return cls(
            device_id=str(value["device_id"]),
            identity_hash=str(value["identity_hash"]),
            config_fingerprint=str(value["config_fingerprint"]),
            enrolled_at_utc=str(value["enrolled_at_utc"]),
            templates=tuple(ChallengeTemplate.from_dict(dict(item)) for item in value["templates"]),
            profile_version=str(value.get("profile_version", "1.0")),
            profile_signature=str(value["profile_signature"]),
        )


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    accepted: bool
    status: str
    device_id: str
    identity_hash: str
    challenge_id: str
    stimulus_digest: str
    masked_hamming_distance: int
    compared_bit_count: int
    hamming_ratio: float
    response_reliability: float
    noise_distance: float
    environment_penalty: float
    clone_likelihood: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    authenticated_at_utc: str = field(default_factory=lambda: utc_now().isoformat(timespec="milliseconds"))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value
