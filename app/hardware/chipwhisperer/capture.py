"""Loading and provenance classification for side-channel trace files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.hardware.common import (
    HardwareIntegrationError,
    load_json,
    require_file,
    sha256_file,
)

_SOURCE_TYPES = {
    "OFFLINE_TRACE",
    "SIMULATED_TRACE",
    "IMPORTED_TRACE",
    "PHYSICAL_CAPTURE",
}


@dataclass(frozen=True, slots=True)
class TraceFileEvidence:
    samples: tuple[float, ...]
    source_type: str
    file_digest: str
    provenance_declared: bool


def load_trace_evidence(
    path: Path,
) -> TraceFileEvidence:
    resolved = require_file(
        path,
        "chipwhisperer",
    )

    data = load_json(
        resolved
    )

    values = data.get(
        "samples"
    )

    if not isinstance(
        values,
        list,
    ):
        raise HardwareIntegrationError(
            "chipwhisperer",
            "trace JSON requires a samples array",
        )

    try:
        samples = tuple(
            float(value)
            for value in values
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HardwareIntegrationError(
            "chipwhisperer",
            "trace contains a non-numeric sample",
        ) from exc

    provenance = data.get(
        "provenance"
    )

    if provenance is None:
        source_type = "OFFLINE_TRACE"
        provenance_declared = False
    else:
        if not isinstance(
            provenance,
            dict,
        ):
            raise HardwareIntegrationError(
                "chipwhisperer",
                "trace provenance must be a JSON object",
            )

        source_type = str(
            provenance.get(
                "source_type",
                "",
            )
        ).strip().upper()

        provenance_declared = True

        if source_type not in _SOURCE_TYPES:
            raise HardwareIntegrationError(
                "chipwhisperer",
                (
                    "trace provenance contains "
                    "an unsupported source_type"
                ),
                {
                    "source_type": source_type,
                },
            )

    return TraceFileEvidence(
        samples=samples,
        source_type=source_type,
        file_digest=sha256_file(
            resolved
        ),
        provenance_declared=provenance_declared,
    )


def load_trace(
    path: Path,
) -> list[float]:
    """Preserve the existing trace-loading API."""

    return list(
        load_trace_evidence(
            path
        ).samples
    )
