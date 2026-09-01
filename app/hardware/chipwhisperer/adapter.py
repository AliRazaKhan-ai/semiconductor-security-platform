from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.hardware.chipwhisperer.analysis import analyse_trace
from app.hardware.chipwhisperer.capture import (
    TraceFileEvidence,
    load_trace_evidence,
)
from app.hardware.chipwhisperer.schemas import (
    ChipWhispererResult,
)
from app.hardware.common import (
    HardwareIntegrationError,
    load_json,
)


class ChipWhispererAdapter:
    def __init__(
        self,
        *,
        anomaly_threshold: float = 0.35,
        allowed_source_types: set[str] | None = None,
    ) -> None:
        self.threshold = anomaly_threshold
        self.allowed_source_types = (
            allowed_source_types
            or {
                "OFFLINE_TRACE",
                "SIMULATED_TRACE",
                "IMPORTED_TRACE",
            }
        )

        if (
            "PHYSICAL_CAPTURE"
            in self.allowed_source_types
        ):
            raise ValueError(

                    "PHYSICAL_CAPTURE cannot be enabled "
                    "because physical ChipWhisperer "
                    "acquisition verification is not implemented"

            )

    @classmethod
    def from_project(
        cls,
        root: Path,
    ) -> ChipWhispererAdapter:
        cfg = load_json(
            root
            / "configs/hardware/chipwhisperer.json"
        )

        values = cfg.get(
            "allowed_source_types",
            [
                "OFFLINE_TRACE",
                "SIMULATED_TRACE",
                "IMPORTED_TRACE",
            ],
        )

        if not isinstance(
            values,
            list,
        ):
            raise HardwareIntegrationError(
                "chipwhisperer",
                (
                    "allowed_source_types "
                    "must be a JSON array"
                ),
            )

        source_types = {
            str(value).strip().upper()
            for value in values
        }

        try:
            return cls(
                anomaly_threshold=float(
                    cfg.get(
                        "anomaly_threshold",
                        0.35,
                    )
                ),
                allowed_source_types=source_types,
            )
        except ValueError as exc:
            raise HardwareIntegrationError(
                "chipwhisperer",
                (
                    "Invalid ChipWhisperer "
                    "provenance configuration"
                ),
            ) from exc

    def _validate_source(
        self,
        evidence: TraceFileEvidence,
        *,
        role: str,
    ) -> None:
        if (
            evidence.source_type
            == "PHYSICAL_CAPTURE"
        ):
            raise HardwareIntegrationError(
                "chipwhisperer",
                (
                    f"{role} claims PHYSICAL_CAPTURE, "
                    "but physical ChipWhisperer capture "
                    "verification is not implemented"
                ),
            )

        if (
            evidence.source_type
            not in self.allowed_source_types
        ):
            raise HardwareIntegrationError(
                "chipwhisperer",
                (
                    f"{role} source type is not allowed"
                ),
                {
                    "source_type": (
                        evidence.source_type
                    ),
                },
            )

    def analyse_files(
        self,
        candidate: Path,
        reference: Path,
    ) -> ChipWhispererResult:
        candidate_evidence = (
            load_trace_evidence(
                candidate
            )
        )

        reference_evidence = (
            load_trace_evidence(
                reference
            )
        )

        self._validate_source(
            candidate_evidence,
            role="candidate trace",
        )

        self._validate_source(
            reference_evidence,
            role="reference trace",
        )

        result = analyse_trace(
            list(
                candidate_evidence.samples
            ),
            list(
                reference_evidence.samples
            ),
            anomaly_threshold=self.threshold,
        )

        return replace(
            result,
            analysis_mode=(
                "FILE_BASED_OFFLINE_ANALYSIS"
            ),
            candidate_source_type=(
                candidate_evidence.source_type
            ),
            reference_source_type=(
                reference_evidence.source_type
            ),
            candidate_file_digest=(
                candidate_evidence.file_digest
            ),
            reference_file_digest=(
                reference_evidence.file_digest
            ),
            physical_capture_verified=False,
        )
