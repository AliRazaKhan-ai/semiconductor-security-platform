from __future__ import annotations

from app.hardware.yosys.schemas import YosysMetrics


def evaluate(metrics:YosysMetrics, policy:dict)->tuple[str,...]:
    reasons=[]
    limits={'cells':metrics.cells,'wire_bits':metrics.wire_bits,'memory_bits':metrics.memory_bits}
    for name,value in limits.items():
        maximum=int(policy.get(f'maximum_{name}',10**9))
        if value>maximum: reasons.append(f'{name.upper()}_LIMIT_EXCEEDED')
    forbidden={str(x) for x in policy.get('forbidden_cell_types',[])}
    if forbidden.intersection(metrics.cell_types): reasons.append('FORBIDDEN_CELL_TYPE')
    required={str(x) for x in policy.get('required_cell_types',[])}
    if not required.issubset(metrics.cell_types): reasons.append('REQUIRED_CELL_TYPE_MISSING')
    return tuple(reasons)


def _cell_family_count(
    metrics: YosysMetrics,
    cell_types: set[str],
) -> int:
    return sum(
        int(metrics.cell_types.get(cell_type, 0))
        for cell_type in cell_types
    )


def structural_delta_summary(
    reference: YosysMetrics,
    candidate: YosysMetrics,
    policy: dict,
) -> dict[str, int]:
    config = policy.get("structural_baseline", {})

    sequential = {
        str(item)
        for item in config.get("sequential_cell_types", [])
    }
    control = {
        str(item)
        for item in config.get("control_cell_types", [])
    }

    return {
        "absolute_cell_delta": abs(
            candidate.cells - reference.cells
        ),
        "absolute_wire_bit_delta": abs(
            candidate.wire_bits - reference.wire_bits
        ),
        "absolute_public_wire_delta": abs(
            candidate.public_wires - reference.public_wires
        ),
        "additional_sequential_cells": max(
            0,
            _cell_family_count(candidate, sequential)
            - _cell_family_count(reference, sequential),
        ),
        "additional_control_cells": max(
            0,
            _cell_family_count(candidate, control)
            - _cell_family_count(reference, control),
        ),
    }


def evaluate_structural_delta(
    reference: YosysMetrics,
    candidate: YosysMetrics,
    policy: dict,
) -> tuple[str, ...]:
    config = policy.get("structural_baseline", {})

    if not isinstance(config, dict):
        return ()

    if not bool(config.get("enabled", False)):
        return ()

    delta = structural_delta_summary(
        reference,
        candidate,
        policy,
    )

    checks = (
        (
            "absolute_cell_delta",
            "maximum_absolute_cell_delta",
            "STRUCTURAL_CELL_DELTA_EXCEEDED",
        ),
        (
            "absolute_wire_bit_delta",
            "maximum_absolute_wire_bit_delta",
            "STRUCTURAL_WIRE_BIT_DELTA_EXCEEDED",
        ),
        (
            "absolute_public_wire_delta",
            "maximum_absolute_public_wire_delta",
            "STRUCTURAL_PUBLIC_WIRE_DELTA_EXCEEDED",
        ),
        (
            "additional_sequential_cells",
            "maximum_additional_sequential_cells",
            "STRUCTURAL_SEQUENTIAL_LOGIC_ADDED",
        ),
        (
            "additional_control_cells",
            "maximum_additional_control_cells",
            "STRUCTURAL_CONTROL_LOGIC_ADDED",
        ),
    )

    reasons = []

    for metric_name, limit_name, reason in checks:
        maximum = int(config.get(limit_name, 10**9))

        if delta[metric_name] > maximum:
            reasons.append(reason)

    return tuple(reasons)
