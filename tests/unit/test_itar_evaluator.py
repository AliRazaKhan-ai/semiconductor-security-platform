"""Tests for ITAR and USML normalization."""

from app.compliance.export_control.itar import (
    evaluate_itar,
    normalize_optional_text,
)


def test_null_like_values_normalize_to_empty() -> None:
    assert normalize_optional_text(None) == ""
    assert normalize_optional_text("None") == ""
    assert normalize_optional_text("null") == ""
    assert normalize_optional_text("unknown") == ""


def test_commercial_chip_is_not_itar_indicated() -> None:
    result = evaluate_itar(
        {
            "usml_category": None,
            "defense_related": False,
            "specially_designed_for_military": False,
        }
    )

    assert result["status"] == "NOT_INDICATED"
    assert result["score"] == 0.1
    assert result["details"]["usml_category"] is None


def test_explicit_usml_category_is_itar_controlled() -> None:
    result = evaluate_itar(
        {
            "usml_category": "XI",
            "defense_related": True,
            "specially_designed_for_military": True,
        }
    )

    assert result["status"] == "ITAR_CONTROLLED"
    assert result["score"] == 1.0
    assert result["details"]["usml_category"] == "XI"
