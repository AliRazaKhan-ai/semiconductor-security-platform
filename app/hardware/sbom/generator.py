"""Purpose: Generate reproducible CycloneDX SBOM documents for chip artefacts.

Directory: app/hardware/sbom
Dependencies: standard library; app.hardware.common; app.hardware.sbom.schemas
Connection: consumed by HardwareSecurityPipeline; document_digest is stored in the
            DigitalTwin record and compared on every subsequent verification

The document digest MUST be reproducible. A twin binds sbom_digest as an invariant, so a
digest that varies between runs makes the digital-twin stage impossible to pass twice.

Three inputs previously made it vary:
  - a fresh uuid4 serial number on every call
  - a wall-clock generation timestamp inside the hashed document
  - each component's absolute filesystem path inside the hashed document

The document is therefore split. The CANONICAL document is hashed and contains only
content-derived values. The PERSISTED document is the canonical document plus generation
metadata that is deliberately excluded from the hash: generatedAt, absolute paths, and the
self-referential digest property. canonical_document() is public so any verifier can
re-derive the digest from a persisted file without guessing what to strip.

An SBOM without a generation time is a weaker artefact; an SBOM whose digest depends on
its generation time is unusable as an invariant. Both properties are retained.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.hardware.common import atomic_write_json, canonical_json, sha256_file
from app.hardware.sbom.schemas import SBOMComponent, SBOMResult

# Fixed namespace for UUIDv5 serial-number derivation. Generated once and never changed:
# altering it would change every serial number and therefore every document digest, which
# would invalidate every existing digital twin. Treat as a permanent constant.
SBOM_SERIAL_NAMESPACE = uuid.UUID("1b8f0f3c-2a47-5d61-9c8e-3f7a6d4b2e10")

SBOM_SPEC_VERSION = "1.5"
SBOM_FORMAT = "CycloneDX"
DOCUMENT_DIGEST_PROPERTY = "semisecure:document-sha256"

# Component properties excluded from the canonical document because they describe where an
# artefact happened to live, not what it is. Including them makes the digest machine-local.
NON_CANONICAL_COMPONENT_PROPERTIES = ("absolute_path",)


def _canonical_component(component: SBOMComponent) -> dict[str, Any]:
    """Return the content-derived view of a component, free of location metadata."""
    payload = component.to_dict()

    properties = payload.get("properties")

    if isinstance(properties, dict):
        payload["properties"] = {
            key: value
            for key, value in properties.items()
            if key not in NON_CANONICAL_COMPONENT_PROPERTIES
        }

    return payload


def component_map(components: list[SBOMComponent]) -> dict[str, str]:
    """Return the sorted {component name: SHA-256} map the serial number is derived from."""
    return {
        component.name: str(component.hashes.get("SHA-256", ""))
        for component in sorted(components, key=lambda item: item.name)
    }


def derive_serial_number(chip_id: str, components: list[SBOMComponent]) -> str:
    """Return a content-derived urn:uuid serial number.

    UUIDv5 over the chip identifier and the sorted component digest map, under a fixed
    namespace. Remains a valid RFC 4122 URN, unlike a bare hash string, and is identical
    for identical inputs on any machine.
    """
    seed = canonical_json(
        {
            "chip_id": str(chip_id),
            "components": component_map(components),
        }
    ).decode("utf-8")

    return f"urn:uuid:{uuid.uuid5(SBOM_SERIAL_NAMESPACE, seed)}"


def canonical_document(
    *,
    chip_id: str,
    components: list[SBOMComponent],
    serial_number: str,
) -> dict[str, Any]:
    """Return the exact document the digest is computed over.

    Public so that a verifier can re-derive document_digest from a persisted SBOM by
    rebuilding this structure, rather than inferring which fields to strip.
    """
    return {
        "bomFormat": SBOM_FORMAT,
        "specVersion": SBOM_SPEC_VERSION,
        "serialNumber": serial_number,
        "version": 1,
        "metadata": {
            "component": {
                "type": "device",
                "name": str(chip_id),
            },
        },
        "components": [
            _canonical_component(component)
            for component in sorted(components, key=lambda item: item.name)
        ],
    }


def document_digest(
    *,
    chip_id: str,
    components: list[SBOMComponent],
    serial_number: str,
) -> str:
    """Return the SHA-256 of the canonical document."""
    return hashlib.sha256(
        canonical_json(
            canonical_document(
                chip_id=chip_id,
                components=components,
                serial_number=serial_number,
            )
        )
    ).hexdigest()


class SBOMGenerator:
    def generate(
        self,
        *,
        chip_id: str,
        artifacts: list[Path],
        output: Path,
        metadata: dict[str, str] | None = None,
    ) -> SBOMResult:
        supplied = metadata or {}
        components: list[SBOMComponent] = []

        for artifact in sorted(
            (path.resolve(strict=True) for path in artifacts),
            key=lambda path: path.name,
        ):
            components.append(
                SBOMComponent(
                    "file",
                    artifact.name,
                    str(supplied.get(f"version:{artifact.name}", "unknown")),
                    str(supplied.get(f"supplier:{artifact.name}", "unknown")),
                    {"SHA-256": sha256_file(artifact)},
                    tuple(),
                    {"absolute_path": str(artifact)},
                )
            )

        serial = derive_serial_number(chip_id, components)

        canonical = canonical_document(
            chip_id=chip_id,
            components=components,
            serial_number=serial,
        )

        digest = hashlib.sha256(canonical_json(canonical)).hexdigest()

        # Persisted record: the canonical document plus generation metadata that is
        # deliberately outside the hash. generatedAt is retained because an SBOM without a
        # generation time is a weaker artefact; it sits beside the canonical content rather
        # than inside it so the digest stays reproducible.
        document = dict(canonical)
        document["generatedAt"] = datetime.now(UTC).isoformat(timespec="seconds")
        document["components"] = [component.to_dict() for component in sorted(components, key=lambda item: item.name)]
        document["properties"] = [
            {
                "name": DOCUMENT_DIGEST_PROPERTY,
                "value": digest,
            },
            {
                "name": "semisecure:digest-scope",
                "value": (
                    "canonical document only; generatedAt, component absolute_path "
                    "and this properties array are excluded from the digest"
                ),
            },
        ]

        atomic_write_json(output, document)

        reasons = tuple(["EMPTY_SBOM"] if not components else [])

        return SBOMResult(
            not reasons,
            "GENERATED" if not reasons else "REJECTED",
            reasons,
            serial,
            len(components),
            digest,
            str(output),
        )
