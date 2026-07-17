"""Regression tests for Phase 3 CLI and export-control corrections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manage import (
    CommandFailure,
    build_compliance_payload,
    validate_scan_id,
)


def test_good_chip_contains_complete_compliance_data() -> None:
    path = Path("data/chips/chip_01_good.json")
    chip = json.loads(path.read_text(encoding="utf-8"))

    assert chip["supplier"]["supplier_id"] == "SUP-DE-001"
    assert chip["supplier"]["country"] == "DE"
    assert chip["compliance"]["eccn"] == "EAR99"
    assert chip["compliance"]["destination_country"] == "DE"
    assert chip["compliance"]["defense_related"] is False


def test_empty_usml_category_is_not_sent() -> None:
    payload = build_compliance_payload(
        "scan-test-12345678",
        {
            "scenario": "GOOD_CHIP",
            "compliance": {
                "subject_to_ear": True,
                "eccn": "EAR99",
                "usml_category": None,
                "destination_country": "DE",
                "defense_related": False,
            },
            "supplier": {
                "supplier_id": "SUP-DE-001",
                "name": "TrustedFab Europe-1",
                "country": "DE",
            },
        },
        anchor_to_blockchain=False,
    )

    assert "usml_category" not in payload["item"]
    assert payload["item"]["defense_related"] is False


@pytest.mark.parametrize(
    "value",
    [
        "paste-the-real-scan-id-here",
        "SCAN-ID-RETURNED-BY-THE-API",
        "ACTUAL_SCAN_ID",
        "YOUR_EXISTING_SCAN_ID",
        "<SCAN_ID>",
    ],
)
def test_documentation_placeholders_are_rejected(
    value: str,
) -> None:
    with pytest.raises(CommandFailure):
        validate_scan_id(value)


def test_real_scan_id_is_accepted() -> None:
    value = "7f697454-4f81-46d5-be9e-d413504f6de7"

    assert validate_scan_id(value) == value
