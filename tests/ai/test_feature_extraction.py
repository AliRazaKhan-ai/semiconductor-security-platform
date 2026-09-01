"""Tests for active and candidate AI feature schemas."""

from __future__ import annotations

import numpy as np

from app.ai.feature_extraction import (
    FEATURE_NAMES,
    FeatureExtractionService,
)
from app.ai.feature_extraction.schemas import (
    CANDIDATE_FEATURE_NAMES,
)


def evidence() -> dict:
    x = np.linspace(
        0,
        10,
        300,
    )

    return {
        "side_channel": {
            "power_trace": np.sin(
                x
            ).tolist(),
            "em_trace": np.cos(
                x
            ).tolist(),
            "timing_trace": (
                1
                + 0.01
                * np.sin(
                    x
                )
            ).tolist(),
        },
        "yosys": {
            # Legacy values remain available while v1 is active.
            "gate_count": 1000,
            "cell_count": 900,
            "unused_logic_ratio": 0.0,
            "rare_net_count": 0,
            "netlist_delta_ratio": 0.0,

            # Verified Yosys-derived candidate values.
            "wire_count": 1500,
            "wire_bit_count": 2200,
            "public_wire_count": 400,
            "memory_bit_count": 128,
            "cell_type_count": 12,
            "sequential_cells": 250,
            "combinational_cells": 650,
        },
        "verilator": {
            "assertion_count": 24,
            "failed_assertions": 0,
        },
        "supply_chain": {},
        "puf": {
            "stability_score": 0.99,
        },
        "opentitan": {
            "verified": True,
        },
    }


def test_complete_active_schema() -> None:
    result = (
        FeatureExtractionService()
        .extract(
            evidence()
        )
    )

    assert (
        result.names
        == FEATURE_NAMES
    )

    assert len(
        result.values
    ) == 32

    assert np.asarray(
        result.sequence
    ).shape == (
        256,
        3,
    )


def test_candidate_schema_uses_verified_yosys_fields() -> None:
    result = FeatureExtractionService(
        feature_names=(
            CANDIDATE_FEATURE_NAMES
        )
    ).extract(
        evidence()
    )

    assert (
        result.names
        == CANDIDATE_FEATURE_NAMES
    )

    assert len(
        result.values
    ) == 32

    values = dict(
        zip(
            result.names,
            result.values,
            strict=True,
        )
    )

    assert (
        values[
            "cell_count_log"
        ]
        > 0.0
    )

    assert (
        values[
            "wire_count_log"
        ]
        > 0.0
    )

    assert (
        values[
            "wire_bit_count_log"
        ]
        > 0.0
    )

    assert (
        0.0
        <= values[
            "public_wire_ratio"
        ]
        <= 1.0
    )

    assert (
        values[
            "memory_bit_count_log"
        ]
        > 0.0
    )


def test_active_and_candidate_schemas_are_distinct() -> None:
    assert (
        FEATURE_NAMES
        != CANDIDATE_FEATURE_NAMES
    )

    assert len(
        FEATURE_NAMES
    ) == len(
        CANDIDATE_FEATURE_NAMES
    ) == 32

    unsupported = {
        "unused_logic_ratio",
        "rare_net_ratio",
        "netlist_delta_ratio",
    }

    assert unsupported.isdisjoint(
        CANDIDATE_FEATURE_NAMES
    )
