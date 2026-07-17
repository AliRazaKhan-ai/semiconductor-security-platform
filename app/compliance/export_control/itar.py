"""Purpose: Evaluate ITAR and USML indicators for semiconductor transactions.
Directory: app/compliance/export_control.
Dependencies: Python standard library.
Connection: Used by the export-control engine to detect ITAR-controlled items.
"""

from __future__ import annotations

from typing import Any


def normalize_optional_text(value: object) -> str:
    """Return an empty string for missing or null-like values."""
    if value is None:
        return ""

    normalized = str(value).strip()

    if normalized.lower() in {
        "",
        "none",
        "null",
        "n/a",
        "unknown",
    }:
        return ""

    return normalized


def evaluate_itar(item: dict[str, Any]) -> dict[str, Any]:
    """Evaluate explicit USML and military-design indicators."""
    usml_category = normalize_optional_text(
        item.get("usml_category")
    )

    defense_related = bool(
        item.get("defense_related", False)
    )

    specially_designed = bool(
        item.get(
            "specially_designed_for_military",
            False,
        )
    )

    indicators: list[str] = []

    if usml_category:
        indicators.append(
            f"Explicit USML category {usml_category}"
        )

    if defense_related:
        indicators.append(
            "Item is identified as defense-related"
        )

    if specially_designed:
        indicators.append(
            "Item is specially designed for military use"
        )

    controlled = bool(indicators)

    return {
        "control": "itar",
        "status": (
            "ITAR_CONTROLLED"
            if controlled
            else "NOT_INDICATED"
        ),
        "score": 1.0 if controlled else 0.1,
        "reasons": (
            indicators
            if indicators
            else [
                "No explicit USML or military-design "
                "indicators were identified"
            ]
        ),
        "details": {
            "usml_category": (
                usml_category or None
            ),
            "defense_related": defense_related,
            "specially_designed_for_military": (
                specially_designed
            ),
        },
    }
