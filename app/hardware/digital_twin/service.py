"""Purpose: Create and verify digital twins against their configured invariants.

Directory: app/hardware/digital_twin
Dependencies: standard library; app.hardware.common; repository, schemas, validator
Connection: constructed by HardwareSecurityPipeline; reads configs/hardware/digital_twin.json

configs/hardware/digital_twin.json declared required_match_fields and repository while the
service hardcoded both, so the file read as authoritative and was inert. Both keys are now
loaded here and the configuration is the source of truth.

A malformed or empty configuration raises at construction rather than falling back to a
default. Silently reverting to a built-in field list when the configured one cannot be read
would weaken a security control without any signal that it had happened; from_project() is
called during pipeline construction, so the failure is visible at start-up instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.hardware.common import HardwareIntegrationError, load_json
from app.hardware.digital_twin.repository import DigitalTwinRepository
from app.hardware.digital_twin.schemas import DigitalTwin, TwinValidationResult
from app.hardware.digital_twin.validator import (
    TwinValidationConfigurationError,
    validate_twin,
)

CONFIG_RELATIVE_PATH = "configs/hardware/digital_twin.json"
DEFAULT_REPOSITORY_RELATIVE_PATH = "data/digital_twins"


class DigitalTwinService:
    def __init__(
        self,
        repository: DigitalTwinRepository,
        required_match_fields: tuple[str, ...] | None = None,
    ) -> None:
        self.repository = repository
        self.required_match_fields = required_match_fields

    @classmethod
    def from_project(cls, root: Path) -> "DigitalTwinService":
        config_path = root / CONFIG_RELATIVE_PATH

        # load_json raises HardwareIntegrationError for a missing or malformed file.
        config = load_json(config_path)

        declared = config.get("required_match_fields")

        if not isinstance(declared, list):
            raise HardwareIntegrationError(
                "digital_twin",
                "required_match_fields must be a JSON array",
                {"config": str(config_path)},
            )

        fields = tuple(str(field).strip() for field in declared if str(field).strip())

        if not fields:
            raise HardwareIntegrationError(
                "digital_twin",
                (
                    "required_match_fields is empty; a digital twin validated "
                    "against no fields would pass unconditionally"
                ),
                {"config": str(config_path)},
            )

        repository_path = str(
            config.get(
                "repository",
                DEFAULT_REPOSITORY_RELATIVE_PATH,
            )
        ).strip()

        if not repository_path:
            raise HardwareIntegrationError(
                "digital_twin",
                "repository path in the digital twin configuration is empty",
                {"config": str(config_path)},
            )

        candidate = Path(repository_path)

        if candidate.is_absolute():
            raise HardwareIntegrationError(
                "digital_twin",
                (
                    "repository path in the digital twin configuration must be "
                    "relative to the project root"
                ),
                {
                    "config": str(config_path),
                    "repository": repository_path,
                },
            )

        return cls(
            DigitalTwinRepository(root / candidate),
            required_match_fields=fields,
        )

    def create(self, **values) -> DigitalTwin:
        now = datetime.now(UTC).isoformat(timespec="milliseconds")

        twin = DigitalTwin(
            schema_version="1.0",
            created_at_utc=now,
            updated_at_utc=now,
            **values,
        )

        self.repository.save(twin)

        return twin

    def verify(
        self,
        twin_id: str,
        evidence: dict[str, str],
    ) -> TwinValidationResult:
        twin = self.repository.load(twin_id)

        try:
            return validate_twin(
                twin,
                evidence,
                required_fields=self.required_match_fields,
            )
        except TwinValidationConfigurationError as exc:
            raise HardwareIntegrationError(
                "digital_twin",
                f"Digital twin comparison field set is invalid: {exc}",
                {"twin_id": twin_id},
            ) from exc
