"""Purpose: Provide the production application facade for PUF enrollment, challenge issue, simulation, and authentication.
Directory: app/hardware/puf.
Dependencies: environment variables, configuration, simulator, verifier, JSON repositories.
Connection: Terminal CLI and pipeline stage use this facade; no web login or SQL is introduced.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

from app.hardware.puf.config import PUFConfig, load_puf_config
from app.hardware.puf.crypto import derive_key, hmac_sha256
from app.hardware.puf.exceptions import PUFConfigurationError, PUFEnrollmentError
from app.hardware.puf.repository import ChallengeLedger, EnrollmentRepository
from app.hardware.puf.schemas import (
    AuthenticationResult,
    EnrollmentProfile,
    PUFChallenge,
    PUFEnvironment,
    PUFResponse,
)
from app.hardware.puf.simulator import ChallengeFactory, HybridPUFSimulator
from app.hardware.puf.verifier import PUFEnrollmentService, PUFVerifier


def _decode_master_secret(raw: str) -> bytes:
    value = raw.strip()
    try:
        if value.startswith("hex:"):
            decoded = bytes.fromhex(value[4:])
        elif value.startswith("base64:"):
            decoded = base64.b64decode(value[7:], validate=True)
        else:
            decoded = value.encode("utf-8")
    except (ValueError, binascii.Error) as exc:
        raise PUFConfigurationError("SEMISURE_PUF_MASTER_SECRET has invalid encoding") from exc
    if len(decoded) < 32:
        raise PUFConfigurationError(
            "SEMISURE_PUF_MASTER_SECRET must contain at least 32 bytes"
        )
    return decoded


class PUFAdapter:
    def __init__(
        self,
        *,
        config: PUFConfig,
        master_secret: bytes,
        project_root: Path,
        enrollment_repository: EnrollmentRepository | None = None,
        challenge_ledger: ChallengeLedger | None = None,
    ) -> None:
        if len(master_secret) < 32:
            raise ValueError("master_secret must contain at least 32 bytes")
        self.config = config
        self.master_secret = master_secret
        self.project_root = project_root.resolve()
        self.issuer_secret = derive_key(master_secret, "puf-challenge-issuer")
        self.template_secret = derive_key(master_secret, "puf-template-protection")
        self.profile_secret = derive_key(master_secret, "puf-profile-signing")
        self.device_secret_root = derive_key(master_secret, "puf-device-root")
        self.challenge_factory = ChallengeFactory(config, self.issuer_secret)
        self.enrollment_repository = enrollment_repository or EnrollmentRepository(
            self._resolve(config.storage.enrollment_root),
            self.project_root / "runtime" / "locks",
        )
        self.challenge_ledger = challenge_ledger or ChallengeLedger(
            self._resolve(config.storage.challenge_ledger_path),
            self.project_root / "runtime" / "locks",
        )
        self.enrollment_service = PUFEnrollmentService(
            config,
            issuer_secret=self.issuer_secret,
            template_secret=self.template_secret,
            profile_secret=self.profile_secret,
        )
        self.verifier = PUFVerifier(
            config,
            issuer_secret=self.issuer_secret,
            template_secret=self.template_secret,
            profile_secret=self.profile_secret,
        )

    @classmethod
    def from_project(
        cls,
        project_root: Path | None = None,
        *,
        master_secret: bytes | None = None,
    ) -> "PUFAdapter":
        root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        config_path = Path(os.getenv("SEMISURE_PUF_CONFIG", "configs/hardware/puf.json"))
        if not config_path.is_absolute():
            config_path = root / config_path
        secret = master_secret
        if secret is None:
            raw = os.getenv("SEMISURE_PUF_MASTER_SECRET")
            if not raw:
                raise PUFConfigurationError(
                    "SEMISURE_PUF_MASTER_SECRET is required for the PUF service"
                )
            secret = _decode_master_secret(raw)
        return cls(
            config=load_puf_config(config_path),
            master_secret=secret,
            project_root=root,
        )

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    def derive_device_secret(self, device_id: str) -> bytes:
        if not device_id or len(device_id) > 128:
            raise ValueError("device_id must contain between 1 and 128 characters")
        return hmac_sha256(self.device_secret_root, b"puf-device", device_id)

    def simulator(self, device_id: str) -> HybridPUFSimulator:
        return HybridPUFSimulator(
            device_id=device_id,
            device_secret=self.derive_device_secret(device_id),
            config=self.config,
        )

    def enroll_device(self, device_id: str, *, replace: bool = False) -> EnrollmentProfile:
        simulator = self.simulator(device_id)
        challenges = tuple(
            self.challenge_factory.issue(sequence=index + 1)
            for index in range(self.config.enrollment.challenge_count)
        )
        profile = self.enrollment_service.enroll(simulator, challenges)
        self.enrollment_repository.save(profile, replace=replace)
        return profile

    def profile(self, device_id: str) -> EnrollmentProfile:
        profile = self.enrollment_repository.load(device_id)
        profile.validate_signature(self.profile_secret)
        return profile

    def issue_challenge(self, device_id: str) -> PUFChallenge:
        profile = self.profile(device_id)
        for template in profile.templates:
            if self.challenge_ledger.status(template.challenge.challenge_id) == "AVAILABLE":
                challenge = template.challenge.reissue(
                    self.issuer_secret,
                    self.config.authentication.challenge_ttl_seconds,
                )
                self.challenge_ledger.issue(
                    challenge.challenge_id,
                    device_id,
                    challenge.expires_at_utc,
                )
                return challenge
        raise PUFEnrollmentError(
            "No unused PUF challenges remain; the device must be securely re-enrolled",
            {"device_id": device_id},
        )

    def simulate_response(
        self,
        device_id: str,
        challenge: PUFChallenge,
        environment: PUFEnvironment | None = None,
        *,
        response_nonce_hex: str | None = None,
    ) -> PUFResponse:
        challenge.validate(self.issuer_secret)
        return self.simulator(device_id).respond(
            challenge,
            environment,
            sample_count=self.config.authentication.response_samples,
            response_nonce_hex=response_nonce_hex,
        )

    def authenticate(
        self,
        device_id: str,
        challenge: PUFChallenge,
        response: PUFResponse,
    ) -> AuthenticationResult:
        profile = self.profile(device_id)
        self.verifier.validate_envelope(profile, challenge, response)
        self.challenge_ledger.consume(
            challenge.challenge_id,
            device_id,
            response.response_digest,
        )
        return self.verifier.authenticate(profile, challenge, response)

    def status(self, device_id: str) -> dict[str, Any]:
        profile = self.profile(device_id)
        challenge_states = [
            self.challenge_ledger.status(template.challenge.challenge_id)
            for template in profile.templates
        ]
        return {
            "device_id": device_id,
            "identity_hash": profile.identity_hash,
            "config_fingerprint": profile.config_fingerprint,
            "enrolled_at_utc": profile.enrolled_at_utc,
            "challenge_bank": {
                "total": len(challenge_states),
                "available": challenge_states.count("AVAILABLE"),
                "issued": challenge_states.count("ISSUED"),
                "consumed": challenge_states.count("CONSUMED"),
            },
        }

    def health(self) -> dict[str, Any]:
        devices = self.enrollment_repository.list_device_ids()
        return {
            "service": "puf",
            "status": "HEALTHY",
            "architecture": "HYBRID_RING_OSCILLATOR_DELAY_CHAIN",
            "configuration_version": self.config.version,
            "config_fingerprint": self.config.fingerprint,
            "enrolled_devices": len(devices),
            "challenge_ledger": self.challenge_ledger.counts(),
            "sql_enabled": False,
            "login_enabled": False,
        }
