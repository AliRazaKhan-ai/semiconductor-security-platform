"""Purpose: Derive side-channel traces from synthesised netlist metrics.

Directory: app/hardware/chipwhisperer
Dependencies: standard library; app.hardware.common.canonical_json
Connection: consumed by scripts/demo/mint_hardware_evidence.py to produce the trace files
            named in each chip fixture's hardware_manifest

DERIVATION CONSTRAINT. generate_samples is a pure function of (metrics, device_seed,
channel). It takes no scenario, no label, no chip identifier, no filename and no path. A
trace whose amplitude followed the fixture's declared scenario would reproduce, one
indirection further away, exactly the defect this project is being reviewed for: a verdict
selected by the input's own label. The netlist metrics are a measurement produced by Yosys
from real RTL; the scenario is not, and it is not visible here.

This is testable by crossing the inputs. Generating with the reference netlist's metrics
and a Trojan fixture's device seed must read as clean. If it does not, the label is
reaching the amplitude through some path other than the metrics.

DERIVATION MODEL. analyse_trace correlates centre-scaled signals, so correlation is
amplitude-invariant and a trace that is merely larger scores near zero anomaly. Structure,
not scale, must carry the difference:

  sequential cells  -> number and relative weight of clock-correlated harmonics
  combinational cells -> broadband content between the harmonics
  total activity    -> amplitude, which reaches the anomaly score through the standard
                       deviation term rather than through correlation

Phase is determined by the metrics. The device seed contributes only bounded jitter and
sample noise, so two devices with identical netlists correlate strongly and the residual
score is the noise floor rather than a signal.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping
from typing import Any

from app.hardware.common import canonical_json

DEFAULT_SAMPLES = 256
CHANNELS = ("power", "em", "timing")

# Yosys cell types with internal state. Counted as sequential; everything else is treated
# as combinational. Prefix matching covers the parameterised variants Yosys emits.
SEQUENTIAL_CELL_PREFIXES = (
    "$adff",
    "$dff",
    "$sdff",
    "$dlatch",
    "$aldff",
    "$mem",
)

# Bounded jitter, in radians, applied to each harmonic's metric-determined phase. Large
# enough that two devices are not bit-identical, small enough that identical netlists still
# correlate strongly. Raising this raises the noise floor and erodes the separation.
PHASE_JITTER_RADIANS = 0.04

# Per-sample noise as a fraction of the amplitude derived from the metrics.
NOISE_FRACTION = 0.02

# Channel weightings. EM emphasises switching edges, so it is differentiated; timing
# reflects sequential depth rather than total activity.
CHANNEL_WEIGHTS: dict[str, dict[str, float]] = {
    "power": {"harmonic": 1.00, "broadband": 0.45, "differentiate": 0.0, "activity": 1.00},
    "em": {"harmonic": 0.70, "broadband": 0.65, "differentiate": 1.0, "activity": 0.55},
    "timing": {"harmonic": 0.35, "broadband": 0.20, "differentiate": 0.0, "activity": 0.20},
}


class TraceDerivationError(ValueError):
    """Raised when the supplied netlist metrics cannot yield a trace."""


def _cell_counts(metrics: Mapping[str, Any]) -> tuple[int, int]:
    """Return (sequential, combinational) cell counts from Yosys cell_types."""
    cell_types = metrics.get("cell_types")

    if not isinstance(cell_types, Mapping):
        raise TraceDerivationError("metrics.cell_types must be a mapping")

    sequential = 0
    total = 0

    for name, count in cell_types.items():
        try:
            value = int(count)
        except (TypeError, ValueError) as exc:
            raise TraceDerivationError(f"cell count for {name} is not an integer") from exc

        if value < 0:
            raise TraceDerivationError(f"cell count for {name} is negative")

        total += value

        if str(name).startswith(SEQUENTIAL_CELL_PREFIXES):
            sequential += value

    if total <= 0:
        raise TraceDerivationError("metrics describe no cells")

    return sequential, total - sequential


def _activity(metrics: Mapping[str, Any]) -> float:
    """Return a switching-activity proxy from cell and wire-bit counts."""
    try:
        cells = int(metrics.get("cells", 0))
        wire_bits = int(metrics.get("wire_bits", 0))
    except (TypeError, ValueError) as exc:
        raise TraceDerivationError("metrics.cells and metrics.wire_bits must be integers") from exc

    if cells <= 0:
        raise TraceDerivationError("metrics.cells must be positive")

    return float(cells) + 0.25 * float(max(0, wire_bits))


def derivation_seed(
    metrics: Mapping[str, Any],
    device_seed: str,
    channel: str,
) -> int:
    """Return the PRNG seed. Derived only from the three declared inputs."""
    return int.from_bytes(
        hashlib.sha256(
            canonical_json(
                {
                    "metrics": dict(metrics),
                    "device_seed": str(device_seed),
                    "channel": str(channel),
                }
            )
        ).digest()[:8],
        "big",
    )


def generate_samples(
    *,
    metrics: Mapping[str, Any],
    device_seed: str,
    channel: str,
    samples: int = DEFAULT_SAMPLES,
) -> list[float]:
    """Return a side-channel trace derived from netlist metrics.

    Pure. The only inputs are the three named arguments. No scenario, label, chip
    identifier, filename or path is accepted, so none can influence the output.
    """
    if channel not in CHANNELS:
        raise TraceDerivationError(f"channel must be one of {CHANNELS}, got {channel!r}")

    if samples < 16:
        raise TraceDerivationError("samples must be at least 16 for trace validation")

    weights = CHANNEL_WEIGHTS[channel]
    sequential, combinational = _cell_counts(metrics)
    activity = _activity(metrics)

    rng = random.Random(derivation_seed(metrics, device_seed, channel))

    # One harmonic per sequential cell, ordered and attenuated. A netlist with more
    # sequential logic therefore occupies more of the spectrum, which correlation sees.
    harmonics = max(1, sequential)
    jitter = [rng.uniform(-PHASE_JITTER_RADIANS, PHASE_JITTER_RADIANS) for _ in range(harmonics)]

    # Broadband weight rises with combinational density relative to sequential logic.
    density = combinational / float(max(1, sequential + combinational))

    amplitude = math.log1p(activity) * weights["activity"]
    noise_scale = amplitude * NOISE_FRACTION

    raw: list[float] = []

    for index in range(samples):
        position = index / float(samples)
        value = 0.0

        for order in range(1, harmonics + 1):
            phase = (order * math.pi) / float(harmonics) + jitter[order - 1]
            value += (
                weights["harmonic"]
                * (1.0 / order)
                * math.sin(2.0 * math.pi * order * position + phase)
            )

        value += weights["broadband"] * density * rng.gauss(0.0, 1.0)
        value = amplitude * value + rng.gauss(0.0, noise_scale)

        raw.append(value)

    if weights["differentiate"] > 0.0:
        differentiated = [raw[0]]
        for index in range(1, samples):
            differentiated.append(
                raw[index]
                + weights["differentiate"] * (raw[index] - raw[index - 1])
            )
        raw = differentiated

    return [round(value, 9) for value in raw]


def build_trace_document(
    *,
    metrics: Mapping[str, Any],
    device_seed: str,
    channel: str,
    netlist_digest: str,
    samples: int = DEFAULT_SAMPLES,
) -> dict[str, Any]:
    """Return a declared SIMULATED_TRACE document ready for load_trace_evidence."""
    sequential, combinational = _cell_counts(metrics)

    return {
        "samples": generate_samples(
            metrics=metrics,
            device_seed=device_seed,
            channel=channel,
            samples=samples,
        ),
        "provenance": {
            "source_type": "SIMULATED_TRACE",
            "channel": channel,
            "generated_by": "app/hardware/chipwhisperer/synthesis_trace.py",
            "physical_capture": False,
            "derivation": "NETLIST_METRIC_DERIVED",
            "derivation_inputs": ["yosys_metrics", "device_seed", "channel"],
            "derivation_excludes": [
                "scenario",
                "expected_results",
                "failure_reason",
                "chip_identifier",
                "file_path",
            ],
            "source_netlist_digest": str(netlist_digest),
            "sequential_cells": sequential,
            "combinational_cells": combinational,
            "activity_proxy": round(_activity(metrics), 6),
            "statement": (
                "Derived from the metrics Yosys produced for the synthesised netlist. "
                "The fixture's declared scenario is not an input to this derivation and "
                "cannot influence the samples. Not a physical capture."
            ),
        },
    }
