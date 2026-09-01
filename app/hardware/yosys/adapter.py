from __future__ import annotations

import hashlib
from pathlib import Path

from app.hardware.common import load_json, sha256_file
from app.hardware.yosys.parser import parse_metrics
from app.hardware.yosys.rules import (
    evaluate,
    evaluate_structural_delta,
    structural_delta_summary,
)
from app.hardware.yosys.runner import YosysRunner
from app.hardware.yosys.schemas import YosysResult


class YosysAdapter:
    def __init__(self, policy: dict, runner: YosysRunner | None = None) -> None:
        self.policy = policy
        self.runner = runner or YosysRunner()

    @classmethod
    def from_project(cls, root: Path) -> "YosysAdapter":
        return cls(load_json(root / "configs/hardware/yosys.json"))

    def analyse(self, rtl: Path, top: str) -> YosysResult:
        stats, log, netlist = self.runner.synthesise(rtl, top)
        metrics = parse_metrics(stats, top)
        reasons = evaluate(metrics, self.policy)
        return YosysResult(
            not reasons,
            "PASS" if not reasons else "FAIL",
            reasons,
            metrics,
            sha256_file(rtl),
            hashlib.sha256(netlist).hexdigest(),
            hashlib.sha256(log.encode()).hexdigest(),
        )

    def analyse_against_reference(
        self,
        candidate_rtl: Path,
        reference_rtl: Path,
        top: str,
    ) -> tuple[YosysResult, dict]:
        """Synthesise a candidate and a known-good reference, then difference the netlists.

        Returns the candidate's standard YosysResult plus a structural delta report.
        A hardware Trojan is characterised by divergence from a known-good baseline, not
        by absolute design size, so this is the only Yosys path that can express it.

        The returned report supplies netlist_delta_ratio for the v2.1 feature schema:
        absolute cell delta normalised by the reference cell count, clamped to [0, 1].
        A ratio of 0.0 means the candidate is structurally identical to the reference.
        """
        candidate_result = self.analyse(candidate_rtl, top)

        reference_stats, reference_log, reference_netlist = self.runner.synthesise(
            reference_rtl, top
        )
        reference_metrics = parse_metrics(reference_stats, top)

        delta = structural_delta_summary(
            reference_metrics,
            candidate_result.metrics,
            self.policy,
        )
        structural_reasons = evaluate_structural_delta(
            reference_metrics,
            candidate_result.metrics,
            self.policy,
        )

        reference_cells = max(1, int(reference_metrics.cells))
        netlist_delta_ratio = min(
            1.0,
            float(delta["absolute_cell_delta"]) / float(reference_cells),
        )

        report = {
            "structural_baseline_enabled": bool(
                self.policy.get("structural_baseline", {}).get("enabled", False)
            ),
            "reference_rtl_digest": sha256_file(reference_rtl),
            "reference_netlist_digest": hashlib.sha256(reference_netlist).hexdigest(),
            "reference_log_digest": hashlib.sha256(reference_log.encode()).hexdigest(),
            "reference_top_module": top,
            "reference_metrics": reference_metrics.to_dict(),
            "candidate_metrics": candidate_result.metrics.to_dict(),
            "delta": dict(delta),
            "netlist_delta_ratio": netlist_delta_ratio,
            "structural_reasons": list(structural_reasons),
            "structural_passed": not structural_reasons,
            "analysis_mode": "REFERENCE_DIFFERENTIAL_SYNTHESIS",
        }

        return candidate_result, report
