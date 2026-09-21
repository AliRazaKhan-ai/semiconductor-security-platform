from __future__ import annotations

import hashlib
from app.hardware.common import CommandRunner, HardwareIntegrationError, require_file
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
        # Reference synthesis results, keyed on the reference RTL's SHA-256. Per
        # instance and in memory: the eight-chip run shares one process, which is
        # where the saving lands.
        self._reference_cache: dict[str, tuple[dict, str, bytes]] = {}

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
        # The reference is the baseline every candidate is judged against. A modified
        # reference would become the new baseline, and a Trojan inserted into both
        # would difference to zero. Its digest must match one pinned in reviewed
        # configuration before anything is synthesised; the chip manifest cannot
        # supply it, because a submitter controls that.
        trusted = self.policy.get("trusted_reference_digests")
        if trusted is not None:
            actual = sha256_file(reference_rtl)
            if actual not in trusted:
                raise HardwareIntegrationError(
                    "yosys",
                    "Reference RTL does not match a trusted digest",
                    {"reference": str(reference_rtl), "sha256": actual},
                )

        candidate_result = self.analyse(candidate_rtl, top)

        # The reference is the same file for every chip, so synthesising it on each
        # scan repeats about half of the 21.4s hardware stage. Measured across the
        # eight fixtures, only chip_02 supplies a distinct candidate RTL; the rest
        # compare the reference against itself.
        #
        # Keyed on the reference file's SHA-256 rather than its path, so a changed
        # file cannot hit a stale entry: a different digest is a different key. The
        # cached value is the raw synthesise() output, so every digest and metric
        # downstream is byte-identical to an uncached run.
        #
        # In memory, on the adapter instance. A disk cache would need invalidation
        # logic, and correctness risk on the control that produces the 8-versus-27
        # cell delta is not worth ten seconds.
        reference_digest = sha256_file(reference_rtl)
        cached = self._reference_cache.get(reference_digest)

        if cached is None:
            cached = self.runner.synthesise(reference_rtl, top)
            self._reference_cache[reference_digest] = cached

        reference_stats, reference_log, reference_netlist = cached
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
            "reference_rtl_digest": reference_digest,
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
