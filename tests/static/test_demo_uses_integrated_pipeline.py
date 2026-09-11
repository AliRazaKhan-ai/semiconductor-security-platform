"""Purpose: Assert the demonstration scripts run the evidence-driven pipeline.
Directory: tests/static.
Dependencies: pytest, re, pathlib.
Connection: Guards the Phase 5 repointing. manage.py pipeline-* routes to
Phase3Orchestrator, whose _ai_result returns verdicts from a scenario-keyed lookup
table and loads no model. A demonstration must not present those as analysis.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "scripts" / "demo"

# An invocation, not a mention. The scripts explain what pipeline-* does and why
# they no longer call it, so matching the bare name would flag its own rationale.
# A command is at the start of a line or after a pipe, semicolon or &&, optionally
# via python/venv, and is not inside an echo.
LEGACY = re.compile(
    r"(?:^|[|;&]\s*)"
    r"(?:\S*python\S*\s+)?"
    r"(?:\./)?manage\.py\s+pipeline-(?:run|all)\b"
)
ECHOED = re.compile(r"^\s*echo\b")


@pytest.mark.security
def test_no_demo_script_invokes_the_legacy_pipeline() -> None:
    offenders: list[str] = []

    for path in sorted(DEMO_DIR.glob("*.sh")):
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            code = line.split("#", 1)[0]
            if ECHOED.match(code):
                continue
            if LEGACY.search(code):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    assert not offenders, (
        "Demonstration scripts must run IntegratedPipelineService, not "
        "Phase3Orchestrator's lookup table. Offenders:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.security
def test_a_demo_script_runs_the_integrated_pipeline() -> None:
    """The guard above is satisfiable by deleting every script; this is not."""
    runner = DEMO_DIR / "run_integrated_demo.sh"
    assert runner.is_file(), f"{runner} is missing"

    source = runner.read_text(encoding="utf-8")
    assert "integrated-run" in source
    assert "mint_hardware_evidence.py" in source
