"""Purpose: Detect when a feature vector falls outside the distribution the models were trained on.
Directory: app/ai/drift.
Dependencies: numpy, json, pathlib.
Connection: Called from AIPipelineService.analyze with the normalized vector.

RISK-09. The normalizer was fitted on a synthetic corpus drawn from a standard normal
distribution while the extractor emitted physical quantities. The two agreed on 34
feature names and nothing else, so the known-good chip was classified TROJAN at 0.9858
with an autoencoder reconstruction error of 162.05 against a threshold of 0.6359. The
cause took a day to trace. A check comparing each incoming vector against the training
support would have flagged it on the first scan.

This reports; it does not decide. Drift means the model is being asked something it was
not trained for, which is an observability signal, not evidence about the chip. A false
drift alarm must not quarantine a part.

Thresholds come from measurement. After the feature contract was fixed, the worst
normalized deviation across the eight fixtures was 2.539. Before the fix it was about
73. Warning at 4.0 and drift at 6.0 sits above normal operation and far below the
broken state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

WARN_DEVIATION = 4.0
DRIFT_DEVIATION = 6.0


@dataclass(frozen=True)
class DriftReport:
    status: str
    worst_feature: str
    worst_deviation: float
    features_beyond_warning: tuple[str, ...] = ()
    detail: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "worst_feature": self.worst_feature,
            "worst_deviation": round(self.worst_deviation, 4),
            "features_beyond_warning": list(self.features_beyond_warning),
            "warn_threshold": WARN_DEVIATION,
            "drift_threshold": DRIFT_DEVIATION,
            "deviations": {k: round(v, 4) for k, v in self.detail.items()},
            "note": (
                "Reported, not enforced. Drift indicates the model is being asked "
                "about a distribution it was not trained on, not that the chip is bad."
            ),
        }


class DriftMonitor:
    """Compare a normalized feature vector against the training support."""

    def __init__(
        self,
        feature_names: tuple[str, ...],
        evidence_root: Path | None = None,
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.evidence_root = evidence_root

    def evaluate(self, normalized: Any) -> DriftReport:
        values = np.asarray(normalized, dtype=float).ravel()

        if values.size != len(self.feature_names):
            return DriftReport(
                status="UNAVAILABLE",
                worst_feature="",
                worst_deviation=0.0,
            )

        deviations = np.abs(values)
        order = int(np.argmax(deviations))
        worst = float(deviations[order])

        beyond = tuple(
            name
            for name, deviation in zip(self.feature_names, deviations, strict=True)
            if deviation >= WARN_DEVIATION
        )

        if worst >= DRIFT_DEVIATION:
            status = "DRIFT"
        elif worst >= WARN_DEVIATION:
            status = "WARNING"
        else:
            status = "WITHIN_TRAINING_SUPPORT"

        report = DriftReport(
            status=status,
            worst_feature=self.feature_names[order],
            worst_deviation=worst,
            features_beyond_warning=beyond,
            detail={
                name: float(deviation)
                for name, deviation in zip(self.feature_names, deviations, strict=True)
                if deviation >= WARN_DEVIATION / 2
            },
        )

        self._record(report)
        return report

    def _record(self, report: DriftReport) -> None:
        """Append non-nominal observations, so the record accumulates across runs."""
        if self.evidence_root is None or report.status == "WITHIN_TRAINING_SUPPORT":
            return

        try:
            self.evidence_root.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                {
                    "observed_at_utc": datetime.now(UTC).isoformat(
                        timespec="milliseconds"
                    ),
                    **report.to_dict(),
                }
            )
            with (self.evidence_root / "drift_observations.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(line + "\n")
        except OSError:
            # Monitoring must never break a scan.
            return
