from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.pipeline.orchestrator import Phase3Orchestrator


@pytest.mark.parametrize(
    ("filename", "stage"),
    [
        (
            "chip_06_counterfeit.json",
            "COUNTERFEIT_AND_CERTIFICATE_VERIFICATION",
        ),
        (
            "chip_07_sanctioned_manufacturer.json",
            "RESTRICTED_PARTY_SCREENING",
        ),
        (
            "chip_08_fake_provenance.json",
            "BLOCKCHAIN_PROVENANCE_RECONCILIATION",
        ),
    ],
)
def test_permanent_rejection_profiles(
    filename: str,
    stage: str,
) -> None:
    simulation = json.loads(
        (Path("data/chips") / filename).read_text(encoding="utf-8")
    )

    result = Phase3Orchestrator._permanent_rejection(simulation)

    assert result is not None
    assert result["stage"] == stage
    assert result["risk_score"] == 1.0


def test_stage_status_and_overall_decision_are_separate() -> None:
    source = Path(
        "app/pipeline/orchestrator.py"
    ).read_text(encoding="utf-8")

    assert 'status="FAILED"' in source
    assert 'run["status"] = "REJECTED"' in source
    assert (
        'run["deployment_decision"] = "REJECTED_PERMANENTLY"'
        in source
    )
    assert 'run["quarantined"] = False' in source
