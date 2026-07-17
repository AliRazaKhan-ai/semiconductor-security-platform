"""Purpose: Enroll PUF identities and perform drift-tolerant, anti-cloning authentication.
Directory: app/hardware/puf.
Dependencies: cryptographic sealing, stability algorithms, simulator, schemas, configuration.
Connection: Adapter orchestrates enrollment and verification; pipeline stage fails closed on rejection.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

from app.hardware.puf.config import PUFConfig
from app.hardware.puf.crypto import (
    bits_to_bytes,
    bytes_to_bits,
    canonical_json,
    hmac_hex,
    seal_bytes,
    sha256_hex,
    unseal_bytes,
)
from app.hardware.puf.exceptions import PUFEnrollmentError, PUFIntegrityError
from app.hardware.puf.schemas import (
    AuthenticationResult,
    ChallengeTemplate,
    EnrollmentProfile,
    PUFChallenge,
    PUFEnvironment,
    PUFResponse,
)
from app.hardware.puf.simulator import HybridPUFSimulator
from app.hardware.puf.stability import (
    clone_likelihood,
    environment_penalty,
    majority_vote,
    masked_hamming_distance,
    normalised_noise_distance,
    reliability_mask,
    shannon_entropy,
    vector_mean,
    vector_scale,
    within_supported_environment,
)


class PUFEnrollmentService:
    def __init__(
        self,
        config: PUFConfig,
        *,
        issuer_secret: bytes,
        template_secret: bytes,
        profile_secret: bytes,
    ) -> None:
        self.config = config
        self.issuer_secret = issuer_secret
        self.template_secret = template_secret
        self.profile_secret = profile_secret

    def enroll(
        self,
        simulator: HybridPUFSimulator,
        challenges: tuple[PUFChallenge, ...],
    ) -> EnrollmentProfile:
        if len(challenges) != self.config.enrollment.challenge_count:
            raise PUFEnrollmentError(
                "Enrollment challenge count does not match policy",
                {
                    "expected": self.config.enrollment.challenge_count,
                    "actual": len(challenges),
                },
            )
        templates = tuple(self._enroll_challenge(simulator, challenge) for challenge in challenges)
        commitments = [template.response_commitment for template in templates]
        identity_hash = sha256_hex(
            canonical_json(
                {
                    "device_id": simulator.device_id,
                    "config_fingerprint": self.config.fingerprint,
                    "response_commitments": commitments,
                }
            )
        )
        profile = EnrollmentProfile(
            device_id=simulator.device_id,
            identity_hash=identity_hash,
            config_fingerprint=self.config.fingerprint,
            enrolled_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds"),
            templates=templates,
        )
        return profile.sign(self.profile_secret)

    def _enroll_challenge(
        self,
        simulator: HybridPUFSimulator,
        challenge: PUFChallenge,
    ) -> ChallengeTemplate:
        challenge.validate(self.issuer_secret, allow_expired=True)
        responses: list[PUFResponse] = []
        for corner_index, (temperature_c, voltage_v) in enumerate(self.config.enrollment.corners):
            response_nonce = hmac_hex(
                self.template_secret,
                b"puf-enrollment-measurement",
                simulator.device_id,
                challenge.stimulus_digest,
                corner_index.to_bytes(4, "big"),
            )[:32]
            responses.append(
                simulator.respond(
                    challenge,
                    PUFEnvironment(temperature_c=temperature_c, voltage_v=voltage_v),
                    sample_count=self.config.enrollment.response_samples,
                    response_nonce_hex=response_nonce,
                )
            )

        reference_bits, cross_corner_reliability = majority_vote(
            [response.response_bits for response in responses]
        )
        combined_reliability = tuple(
            min(
                cross_corner_reliability[index],
                *(response.bit_reliability[index] for response in responses),
            )
            for index in range(len(reference_bits))
        )
        mask = reliability_mask(
            combined_reliability,
            self.config.enrollment.minimum_bit_reliability,
        )
        stable_bit_count = mask.count("1")
        stable_ratio = stable_bit_count / len(mask)
        if stable_ratio < self.config.enrollment.minimum_stable_bit_ratio:
            raise PUFEnrollmentError(
                "PUF does not provide enough stable bits across enrollment corners",
                {
                    "challenge_id": challenge.challenge_id,
                    "stable_bits": stable_bit_count,
                    "total_bits": len(mask),
                    "stable_ratio": stable_ratio,
                    "required_ratio": self.config.enrollment.minimum_stable_bit_ratio,
                },
            )
        stable_response = "".join(
            reference_bits[index] for index, selected in enumerate(mask) if selected == "1"
        )
        if shannon_entropy(stable_response) < 0.35:
            raise PUFEnrollmentError(
                "PUF stable response is excessively biased",
                {"challenge_id": challenge.challenge_id},
            )

        context = bytes.fromhex(challenge.stimulus_digest)
        sealed_reference, seal_tag = seal_bytes(
            self.template_secret,
            bits_to_bytes(reference_bits),
            context,
        )
        commitment = hmac_hex(
            self.template_secret,
            b"puf-reference-commitment",
            context,
            bits_to_bytes(reference_bits),
            mask,
        )
        noise_vectors = [response.noise_signature.components for response in responses]
        return ChallengeTemplate(
            challenge=challenge,
            sealed_reference_hex=sealed_reference,
            seal_tag_hex=seal_tag,
            reliability_mask=mask,
            stable_bit_count=stable_bit_count,
            minimum_reliability=self.config.authentication.minimum_response_reliability,
            maximum_hamming_ratio=self.config.authentication.maximum_masked_hamming_ratio,
            reference_noise_vector=vector_mean(noise_vectors),
            noise_scale_vector=vector_scale(noise_vectors, floor=0.01),
            response_commitment=commitment,
        )


class PUFVerifier:
    def __init__(
        self,
        config: PUFConfig,
        *,
        issuer_secret: bytes,
        template_secret: bytes,
        profile_secret: bytes,
    ) -> None:
        self.config = config
        self.issuer_secret = issuer_secret
        self.template_secret = template_secret
        self.profile_secret = profile_secret

    def validate_envelope(
        self,
        profile: EnrollmentProfile,
        challenge: PUFChallenge,
        response: PUFResponse,
    ) -> ChallengeTemplate:
        profile.validate_signature(self.profile_secret)
        if not hmac.compare_digest(profile.config_fingerprint, self.config.fingerprint):
            raise PUFIntegrityError(
                "PUF profile configuration fingerprint does not match the running service"
            )
        challenge.validate(self.issuer_secret)
        response.validate()
        if response.challenge_id != challenge.challenge_id:
            raise PUFIntegrityError("PUF response challenge identifier does not match")
        if not hmac.compare_digest(response.challenge_digest, challenge.challenge_digest):
            raise PUFIntegrityError("PUF response challenge digest does not match")
        if not hmac.compare_digest(response.stimulus_digest, challenge.stimulus_digest):
            raise PUFIntegrityError("PUF response stimulus digest does not match")
        template = next(
            (
                item
                for item in profile.templates
                if hmac.compare_digest(item.challenge.stimulus_digest, challenge.stimulus_digest)
            ),
            None,
        )
        if template is None:
            raise PUFIntegrityError("PUF challenge does not belong to the enrolled device")
        if template.challenge.challenge_id != challenge.challenge_id:
            raise PUFIntegrityError("PUF challenge identifier differs from the enrolled challenge bank")
        return template

    def authenticate(
        self,
        profile: EnrollmentProfile,
        challenge: PUFChallenge,
        response: PUFResponse,
    ) -> AuthenticationResult:
        template = self.validate_envelope(profile, challenge, response)
        context = bytes.fromhex(challenge.stimulus_digest)
        reference_bits = bytes_to_bits(
            unseal_bytes(
                self.template_secret,
                template.sealed_reference_hex,
                template.seal_tag_hex,
                context,
            )
        )
        if len(reference_bits) != len(response.response_bits):
            raise PUFIntegrityError("PUF response width differs from the enrollment template")
        commitment = hmac_hex(
            self.template_secret,
            b"puf-reference-commitment",
            context,
            bits_to_bytes(reference_bits),
            template.reliability_mask,
        )
        if not hmac.compare_digest(commitment, template.response_commitment):
            raise PUFIntegrityError("PUF reference commitment is invalid")

        distance, compared_bits, hamming_ratio = masked_hamming_distance(
            reference_bits,
            response.response_bits,
            template.reliability_mask,
        )
        selected_reliability = [
            response.bit_reliability[index]
            for index, selected in enumerate(template.reliability_mask)
            if selected == "1"
        ]
        response_reliability = sum(selected_reliability) / len(selected_reliability)
        noise_distance = normalised_noise_distance(
            template.reference_noise_vector,
            response.noise_signature.components,
            template.noise_scale_vector,
        )
        env_penalty = environment_penalty(response.environment, self.config)
        reasons: list[str] = []
        if not within_supported_environment(response.environment, self.config):
            reasons.append("UNSUPPORTED_ENVIRONMENT")
        if env_penalty > self.config.authentication.maximum_environment_penalty:
            reasons.append("EXCESSIVE_ENVIRONMENT_DRIFT")
        if response_reliability < template.minimum_reliability:
            reasons.append("LOW_RESPONSE_RELIABILITY")
        if hamming_ratio > template.maximum_hamming_ratio:
            reasons.append("RESPONSE_MISMATCH")
        if noise_distance > self.config.authentication.maximum_noise_distance:
            reasons.append("NOISE_SIGNATURE_MISMATCH")

        accepted = not reasons
        if accepted:
            status = "AUTHENTICATED"
        elif "RESPONSE_MISMATCH" in reasons or "NOISE_SIGNATURE_MISMATCH" in reasons:
            status = "REJECTED_POSSIBLE_CLONE"
        elif "UNSUPPORTED_ENVIRONMENT" in reasons or "EXCESSIVE_ENVIRONMENT_DRIFT" in reasons:
            status = "REJECTED_ENVIRONMENT"
        else:
            status = "REJECTED_UNSTABLE"
        return AuthenticationResult(
            accepted=accepted,
            status=status,
            device_id=profile.device_id,
            identity_hash=profile.identity_hash,
            challenge_id=challenge.challenge_id,
            stimulus_digest=challenge.stimulus_digest,
            masked_hamming_distance=distance,
            compared_bit_count=compared_bits,
            hamming_ratio=hamming_ratio,
            response_reliability=response_reliability,
            noise_distance=noise_distance,
            environment_penalty=env_penalty,
            clone_likelihood=clone_likelihood(
                hamming_ratio,
                template.maximum_hamming_ratio,
            ),
            reasons=tuple(reasons),
        )
