"""Purpose: Resolve a supplier's threat intelligence score from a sourced indicator list.
Directory: app/compliance/threat_intelligence.
Dependencies: json, pathlib, rapidfuzz.
Connection: consulted by SupplierRiskEngine before falling back to the declared value.

threat_intel_score carries weight 0.15 in the supplier risk model and was read
straight from the submitted supplier block: a scored input with no provenance, which
is an assertion by the submitter rather than intelligence.

This resolves the score from data/compliance/threat_intelligence/indicators.json,
which carries its own source, retrieval date and refresh cadence, and returns the
reason a score was assigned. It follows the pattern already used for the Consolidated
Screening List: a file-backed list with a provenance header, matched by name.

No live feed is called. There is no subscription, and a network call inside the scan
path would make an air-gapped run fail. A deployment would populate the file from a
subscribed feed on a stated cadence; the resolution logic would not change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

INDICATORS = Path("data/compliance/threat_intelligence/indicators.json")
MATCH_THRESHOLD = 90


@dataclass(frozen=True, slots=True)
class ThreatAssessment:
    score: float
    source: str
    category: str
    reason: str
    matched: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "source": self.source,
            "category": self.category,
            "reason": self.reason,
            "matched": self.matched,
            "confidence": round(self.confidence, 2),
        }


class ThreatIntelligenceProvider:
    """Look a supplier up in the indicator list. Never raises."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or INDICATORS
        self._document: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._document = {}

    @property
    def source(self) -> str:
        return str(self._document.get("source", "unavailable"))

    @property
    def available(self) -> bool:
        return bool(self._document.get("indicators"))

    def assess(self, supplier_name: str) -> ThreatAssessment | None:
        """Return an assessment, or None when the supplier is not listed.

        None means no indicator, not a score of zero: the caller decides whether
        absence of intelligence is absence of risk.
        """
        name = str(supplier_name or "").strip()
        if not name or not self.available:
            return None

        best: tuple[float, dict[str, Any]] | None = None

        for indicator in self._document.get("indicators", []):
            confidence = float(fuzz.WRatio(name.upper(), str(indicator.get("name", "")).upper()))
            if confidence >= MATCH_THRESHOLD and (best is None or confidence > best[0]):
                best = (confidence, indicator)

        if best is None:
            return None

        confidence, indicator = best

        return ThreatAssessment(
            score=float(indicator.get("score", 0.0)),
            source=self.source,
            category=str(indicator.get("category", "UNCATEGORISED")),
            reason=str(indicator.get("reason", "")),
            matched=str(indicator.get("name", "")),
            confidence=confidence,
        )

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "source": self.source,
            "retrieved_at_utc": self._document.get("retrieved_at_utc"),
            "refresh_cadence": self._document.get("refresh_cadence"),
            "indicator_count": len(self._document.get("indicators", [])),
            "match_threshold": MATCH_THRESHOLD,
        }
