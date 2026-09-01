from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from app.hardware.common import (
    HardwareIntegrationError,
    load_json,
    require_file,
)
from app.hardware.opentitan.attestation import (
    OpenTitanAttestationVerifier,
)
from app.hardware.opentitan.schemas import (
    OpenTitanEvidence,
    OpenTitanResult,
)


def _decode_verification_key(
    raw: str,
) -> bytes:
    try:
        if raw.startswith("base64:"):
            return base64.b64decode(
                raw[7:],
                validate=True,
            )

        if raw.startswith("hex:"):
            return bytes.fromhex(
                raw[4:]
            )

        return raw.encode(
            "utf-8"
        )
    except (
        binascii.Error,
        ValueError,
    ) as exc:
        raise HardwareIntegrationError(
            "opentitan",
            "Invalid OpenTitan verification key encoding",
        ) from exc


class OpenTitanAdapter:
    def __init__(
        self,
        verifier: OpenTitanAttestationVerifier,
    ) -> None:
        self.verifier = verifier

    @classmethod
    def from_project(
        cls,
        project_root: Path,
    ) -> OpenTitanAdapter:
        root = (
            project_root
            .expanduser()
            .resolve()
        )

        cfg = load_json(
            root
            / "configs/hardware/opentitan.json"
        )

        raw = os.getenv(
            "SEMISURE_OPENTITAN_VERIFICATION_KEY",
            "",
        )

        if not raw:
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "SEMISURE_OPENTITAN_VERIFICATION_KEY "
                    "is required"
                ),
            )

        key = _decode_verification_key(
            raw
        )

        trusted = cfg.get(
            "trusted_firmware_digests"
        )

        states = cfg.get(
            "allowed_lifecycle_states"
        )

        if not isinstance(
            trusted,
            list,
        ):
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "trusted_firmware_digests "
                    "must be a JSON array"
                ),
            )

        if not isinstance(
            states,
            list,
        ):
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "allowed_lifecycle_states "
                    "must be a JSON array"
                ),
            )

        replay_value = str(
            cfg.get(
                "replay_state_path",
                (
                    "data/hardware/"
                    "opentitan-replay.json"
                ),
            )
        ).strip()

        if not replay_value:
            raise HardwareIntegrationError(
                "opentitan",
                "OpenTitan replay_state_path is required",
            )

        replay_path = (
            root
            / replay_value
        ).resolve()

        if not replay_path.is_relative_to(
            root
        ):
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "OpenTitan replay_state_path "
                    "must remain inside the project"
                ),
            )

        try:
            verifier = (
                OpenTitanAttestationVerifier(
                    trusted_firmware_digests={
                        str(value)
                        for value in trusted
                    },
                    verification_key=key,
                    allowed_lifecycle_states={
                        str(value)
                        for value in states
                    },
                    minimum_counter=int(
                        cfg.get(
                            "minimum_counter",
                            0,
                        )
                    ),
                    minimum_nonce_bytes=int(
                        cfg.get(
                            "minimum_nonce_bytes",
                            16,
                        )
                    ),
                    maximum_attestation_age_seconds=int(
                        cfg.get(
                            (
                                "maximum_"
                                "attestation_age_seconds"
                            ),
                            300,
                        )
                    ),
                    maximum_future_skew_seconds=int(
                        cfg.get(
                            "maximum_future_skew_seconds",
                            30,
                        )
                    ),
                    replay_state_path=replay_path,
                )
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "Invalid OpenTitan "
                    "attestation configuration"
                ),
                {
                    "error_type": (
                        type(exc).__name__
                    ),
                },
            ) from exc

        return cls(
            verifier
        )

    def verify_file(
        self,
        path: Path,
    ) -> OpenTitanResult:
        data = load_json(
            require_file(
                path,
                "opentitan",
            )
        )

        required_fields = (
            "device_id",
            "lifecycle_state",
            "boot_stage",
            "rom_digest",
            "firmware_digest",
            "otp_digest",
            "monotonic_counter",
            "nonce",
            "signature",
            "timestamp_utc",
        )

        missing = [
            field
            for field in required_fields
            if field not in data
        ]

        if missing:
            raise HardwareIntegrationError(
                "opentitan",
                "OpenTitan evidence is incomplete",
                {
                    "missing_fields": missing,
                },
            )

        certificate_chain = data.get(
            "certificate_chain",
            [],
        )

        if not isinstance(
            certificate_chain,
            list,
        ):
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "OpenTitan certificate_chain "
                    "must be a JSON array"
                ),
            )

        try:
            evidence = OpenTitanEvidence(
                device_id=str(
                    data["device_id"]
                ),
                lifecycle_state=str(
                    data["lifecycle_state"]
                ),
                boot_stage=str(
                    data["boot_stage"]
                ),
                rom_digest=str(
                    data["rom_digest"]
                ),
                firmware_digest=str(
                    data["firmware_digest"]
                ),
                otp_digest=str(
                    data["otp_digest"]
                ),
                monotonic_counter=int(
                    data["monotonic_counter"]
                ),
                nonce=str(
                    data["nonce"]
                ),
                signature=str(
                    data["signature"]
                ),
                certificate_chain=tuple(
                    str(value)
                    for value
                    in certificate_chain
                ),
                timestamp_utc=str(
                    data["timestamp_utc"]
                ),
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise HardwareIntegrationError(
                "opentitan",
                (
                    "OpenTitan evidence contains "
                    "invalid field values"
                ),
                {
                    "error_type": (
                        type(exc).__name__
                    ),
                },
            ) from exc

        return self.verifier.verify(
            evidence
        )
