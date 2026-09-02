"""Purpose: Validate a chip's runtime evidence against its persisted digital twin.

Directory: app/hardware/digital_twin
Dependencies: standard library; app.hardware.common; app.hardware.digital_twin.schemas
Connection: called by DigitalTwinService.verify; the field list is supplied from
            configs/hardware/digital_twin.json required_match_fields

The comparison set was previously a hardcoded tuple while the configuration file declared
required_match_fields that nothing read. A configuration key that looks authoritative and
is inert is worse than no key at all, so the list is now a parameter and the config is the
source of truth.

Two failure modes are kept distinct. A field the twin and the evidence both carry, with
differing values, is a MISMATCH: the artefact is not the one the twin was created for. A
field named in the configuration but absent from the evidence is ABSENT_FROM_EVIDENCE: the
configuration asks for a comparison the pipeline does not supply. Reporting the second as a
mismatch against an empty string hides a configuration error inside a security finding.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from app.hardware.common import canonical_json
from app.hardware.digital_twin.schemas import DigitalTwin, TwinValidationResult

# Retained as the default so existing callers are unaffected. The configuration file is
# authoritative once DigitalTwinService supplies its list.
DEFAULT_REQUIRED_MATCH_FIELDS: tuple[str, ...] = (
    "chip_id",
    "puf_identity_hash",
    "rtl_digest",
    "netlist_digest",
    "firmware_digest",
    "sbom_digest",
)


class TwinValidationConfigurationError(ValueError):
    """Raised when the requested comparison field set cannot be applied to a twin."""


def resolve_required_fields(
    twin: DigitalTwin,
    required_fields: Sequence[str] | None,
) -> tuple[str, ...]:
    """Return the validated comparison field set.

    An empty set is rejected rather than defaulted: a twin validated against no fields
    passes unconditionally, which is a silent removal of the control.
    """
    if required_fields is None:
        fields = DEFAULT_REQUIRED_MATCH_FIELDS
    else:
        fields = tuple(str(field) for field in required_fields)

    if not fields:
        raise TwinValidationConfigurationError(
            "required_match_fields is empty; a digital twin validated against no "
            "fields would pass unconditionally"
        )

    unknown = [field for field in fields if not hasattr(twin, field)]

    if unknown:
        raise TwinValidationConfigurationError(
            "required_match_fields names attributes that do not exist on DigitalTwin: "
            + ", ".join(sorted(unknown))
        )

    duplicates = sorted({field for field in fields if fields.count(field) > 1})

    if duplicates:
        raise TwinValidationConfigurationError(
            "required_match_fields contains duplicates: " + ", ".join(duplicates)
        )

    return fields


def validate_twin(
    twin: DigitalTwin,
    evidence: dict[str, str],
    required_fields: Sequence[str] | None = None,
) -> TwinValidationResult:
    """Compare runtime evidence against the twin over the configured field set."""
    fields = resolve_required_fields(twin, required_fields)

    mismatches: dict[str, dict[str, str]] = {}
    reasons: list[str] = []

    for field in fields:
        expected = str(getattr(twin, field))

        if field not in evidence:
            mismatches[field] = {
                "expected": expected,
                "actual": "",
                "detail": "field is not present in the supplied evidence",
            }
            reasons.append(f"{field.upper()}_ABSENT_FROM_EVIDENCE")
            continue

        actual = str(evidence[field])

        if expected != actual:
            mismatches[field] = {
                "expected": expected,
                "actual": actual,
                "detail": "evidence does not match the twin record",
            }
            reasons.append(f"{field.upper()}_MISMATCH")

    digest = hashlib.sha256(canonical_json(twin.to_dict())).hexdigest()

    return TwinValidationResult(
        not reasons,
        "VERIFIED" if not reasons else "MISMATCH",
        tuple(reasons),
        digest,
        mismatches,
    )
