"""Extract legacy and candidate design-security features from verified EDA evidence."""

from __future__ import annotations

import math
from typing import Any

from app.ai.common import clamp, finite_float


def _nonnegative(
    value: object,
    name: str,
) -> float:
    return max(
        0.0,
        finite_float(
            value,
            name,
        ),
    )


def _bounded_log_count(
    value: float,
) -> float:
    return clamp(
        math.log1p(
            max(
                0.0,
                value,
            )
        )
        / 20.0
    )


def extract_design(
    evidence: dict[str, Any],
) -> dict[str, float]:
    yosys = dict(
        evidence.get(
            "yosys",
            {},
        )
    )

    ver = dict(
        evidence.get(
            "verilator",
            {},
        )
    )

    # Legacy v1 contract. Retained only while the existing models remain active.
    legacy_gates = _nonnegative(
        yosys.get(
            "gate_count",
            0,
        ),
        "gate_count",
    )

    cells = _nonnegative(
        yosys.get(
            "cell_count",
            legacy_gates,
        ),
        "cell_count",
    )

    legacy_denominator = max(
        1.0,
        cells,
    )

    # Candidate v2 values. Every field is derivable from the current Yosys result.
    wires = _nonnegative(
        yosys.get(
            "wire_count",
            0,
        ),
        "wire_count",
    )

    wire_bits = _nonnegative(
        yosys.get(
            "wire_bit_count",
            0,
        ),
        "wire_bit_count",
    )

    public_wires = _nonnegative(
        yosys.get(
            "public_wire_count",
            0,
        ),
        "public_wire_count",
    )

    memory_bits = _nonnegative(
        yosys.get(
            "memory_bit_count",
            0,
        ),
        "memory_bit_count",
    )

    cell_type_count = _nonnegative(
        yosys.get(
            "cell_type_count",
            0,
        ),
        "cell_type_count",
    )

    sequential_cells = _nonnegative(
        yosys.get(
            "sequential_cells",
            0,
        ),
        "sequential_cells",
    )

    combinational_cells = _nonnegative(
        yosys.get(
            "combinational_cells",
            0,
        ),
        "combinational_cells",
    )

    cell_denominator = max(
        1.0,
        cells,
    )

    wire_denominator = max(
        1.0,
        wires,
    )

    assertion_count = _nonnegative(
        ver.get(
            "assertion_count",
            1,
        ),
        "assertion_count",
    )

    failed_assertions = _nonnegative(
        ver.get(
            "failed_assertions",
            0,
        ),
        "failed_assertions",
    )

    return {
        # Legacy v1 model contract.
        "gate_count_log": (
            math.log1p(
                legacy_gates
            )
            / 20.0
        ),
        "cell_type_diversity": clamp(
            cell_type_count
            / 64.0
        ),
        "unused_logic_ratio": clamp(
            finite_float(
                yosys.get(
                    "unused_logic_ratio",
                    0,
                ),
                "unused_logic_ratio",
            )
        ),
        "rare_net_ratio": clamp(
            finite_float(
                yosys.get(
                    "rare_net_count",
                    0,
                ),
                "rare_net_count",
            )
            / legacy_denominator
        ),
        "sequential_ratio": clamp(
            sequential_cells
            / cell_denominator
        ),
        "combinational_ratio": clamp(
            combinational_cells
            / cell_denominator
        ),
        "netlist_delta_ratio": clamp(
            finite_float(
                yosys.get(
                    "netlist_delta_ratio",
                    0,
                ),
                "netlist_delta_ratio",
            )
        ),
        "simulation_failure_ratio": clamp(
            failed_assertions
            / max(
                1.0,
                assertion_count,
            )
        ),

        # Candidate v2 contract.
        "cell_count_log": (
            _bounded_log_count(
                cells
            )
        ),
        "wire_count_log": (
            _bounded_log_count(
                wires
            )
        ),
        "wire_bit_count_log": (
            _bounded_log_count(
                wire_bits
            )
        ),
        "public_wire_ratio": clamp(
            public_wires
            / wire_denominator
        ),
        "memory_bit_count_log": (
            _bounded_log_count(
                memory_bits
            )
        ),
    }
