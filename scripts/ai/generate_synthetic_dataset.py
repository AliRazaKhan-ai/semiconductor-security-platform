"""Purpose: Generate the synthetic training corpus by feature name against a declared schema.

Directory: scripts/ai
Dependencies: numpy; app.ai.feature_extraction.schemas (only when --schema-attr is used)
Connection: produces the .npz consumed by scripts/ai/train_*.py and scripts/ai/dataset.py

Columns are resolved by feature NAME from the selected schema, never by fixed index, so a
schema change cannot silently reassign a feature's meaning. Every run writes a sibling
manifest recording the seed, schema, effect sizes, boosted feature names and output digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SEQUENCE_LENGTH = 256
SEQUENCE_CHANNELS = 3

CLASS_LABELS = ("CLEAN", "TROJAN", "TAMPERED")
DEFAULT_CLASS_WEIGHTS = (0.55, 0.25, 0.20)

# Class 1 (TROJAN) discriminators, by name.
# "legacy" reproduces the original index set [2, 3, 18, 19, 22].
# "extended" additionally boosts simulation_failure_ratio, which the real chip fixtures
# do discriminate on (0.1368 for the trojan fixture against 0.0 for the clean one).
TROJAN_FEATURES_LEGACY = (
    "power_rms",
    "power_peak_to_peak",
    "unused_logic_ratio",
    "rare_net_ratio",
    "netlist_delta_ratio",
)
TROJAN_FEATURES_EXTENDED = TROJAN_FEATURES_LEGACY + ("simulation_failure_ratio",)

# Class 2 (TAMPERED) discriminators, by name. Original index set [24, 25, 26, 28, 29].
SUPPLY_CHAIN_FEATURES = (
    "supplier_risk",
    "country_risk",
    "custody_gap_ratio",
    "sbom_mismatch_ratio",
    "threat_intel_score",
)


class GeneratorError(RuntimeError):
    """Raised when the requested schema or feature selection cannot be satisfied."""


def resolve_feature_names(
    schema_attr: str | None,
    explicit: str | None,
) -> tuple[str, tuple[str, ...]]:
    """Return (schema_label, feature_names) from a schema attribute or an explicit list."""
    if explicit:
        names = tuple(part.strip() for part in explicit.split(",") if part.strip())
        if not names:
            raise GeneratorError("--features was provided but contained no names")
        return "explicit", names

    if not schema_attr:
        raise GeneratorError("one of --schema-attr or --features is required")

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from app.ai.feature_extraction import schemas
    except ImportError as exc:
        raise GeneratorError(
            f"cannot import app.ai.feature_extraction.schemas from {PROJECT_ROOT}"
        ) from exc

    value = getattr(schemas, schema_attr, None)
    if not value:
        available = sorted(
            name
            for name in dir(schemas)
            if name.isupper() and isinstance(getattr(schemas, name), tuple)
        )
        raise GeneratorError(
            f"schemas.{schema_attr} is not defined. Available tuples: {available}"
        )

    return schema_attr, tuple(str(name) for name in value)


def select_boost_indices(
    feature_names: tuple[str, ...],
    boost_names: tuple[str, ...],
    excluded: frozenset[str],
    role: str,
) -> tuple[list[int], list[str], list[str]]:
    """Map boost feature names onto column indices, reporting excluded and absent names."""
    indices: list[int] = []
    applied: list[str] = []
    absent: list[str] = []

    for name in boost_names:
        if name in excluded:
            continue
        if name not in feature_names:
            absent.append(name)
            continue
        indices.append(feature_names.index(name))
        applied.append(name)

    if not indices:
        raise GeneratorError(
            f"no {role} discriminators remain after schema and exclusion filtering"
        )

    return indices, applied, absent


def build_dataset(
    *,
    feature_names: tuple[str, ...],
    samples: int,
    seed: int,
    class_weights: tuple[float, ...],
    trojan_indices: list[int],
    supply_indices: list[int],
    trojan_effect: float,
    supply_effect: float,
    label_noise: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate the feature matrix, sequence tensor and label vector."""
    rng = np.random.default_rng(seed)

    labels = rng.choice(len(class_weights), size=samples, p=class_weights)

    features = rng.normal(0.0, 1.0, (samples, len(feature_names)))
    sequences = rng.normal(
        0.0, 1.0, (samples, SEQUENCE_LENGTH, SEQUENCE_CHANNELS)
    )

    trojan_wave = np.sin(np.linspace(0.0, 24.0 * np.pi, SEQUENCE_LENGTH))
    sequence_scale = trojan_effect / 2.0

    for row, label in enumerate(labels):
        if label == 1:
            features[row, trojan_indices] += trojan_effect
            sequences[row, :, 0] += 0.8 * sequence_scale * trojan_wave
        elif label == 2:
            features[row, supply_indices] += supply_effect
            sequences[row, 80:120, 1] += 2.5 * sequence_scale

    if label_noise > 0.0:
        flip = rng.random(samples) < label_noise
        if flip.any():
            labels[flip] = rng.choice(len(class_weights), size=int(flip.sum()))

    return (
        features.astype(np.float64),
        sequences.astype(np.float32),
        labels.astype(np.int64),
    )


# --- Physical features produced by the production extractor -----------------
#
# build_dataset draws every feature from N(0,1). The production extractor computes
# physical quantities from traces, so a corpus generated that way and a chip analysed
# at run time occupy different spaces that merely share 34 names. Measured on the eight
# fixture trace sets: power_peak_to_peak 11.28-16.19 and em_peak_to_peak 10.51-20.65
# against a corpus range of roughly -4 to +5.
#
# build_dataset_from_traces synthesises traces and calls extract_physical, so the 16
# physical columns are produced by the same code that serves them. Trace parameters below
# are measured from hardware_lab/chipwhisperer/reference_traces, not chosen.
#
# The 18 design and supply features are drawn in [0,1] because extract_design and
# extract_supply_chain clamp to that interval.

TRACE_LENGTH = 256

# Netlist-metric profiles read from the fixture trace provenance. generate_samples is a
# pure function of (metrics, device_seed, channel), so the corpus and the fixtures are
# produced by the same code from the same kind of input.
TRACE_PROVENANCE_ROOT = (
    PROJECT_ROOT / "hardware_lab" / "chipwhisperer" / "reference_traces"
)
TROJAN_FIXTURE = "CHIP-PROD-TROJAN-002"

METRIC_JITTER = 0.18  # relative spread applied to each profile


def read_metric_profiles() -> tuple[dict[str, float], dict[str, float]]:
    """Return (clean, trojan) cell-count profiles from the fixture trace provenance."""
    clean: list[dict[str, float]] = []
    trojan: dict[str, float] | None = None

    for directory in sorted(p for p in TRACE_PROVENANCE_ROOT.iterdir() if p.is_dir()):
        document = directory / "side_channel_trace.json"
        if not document.is_file():
            continue
        provenance = json.loads(document.read_text(encoding="utf-8")).get("provenance", {})
        sequential = float(provenance.get("sequential_cells", 0))
        combinational = float(provenance.get("combinational_cells", 0))
        activity = float(provenance.get("activity_proxy", 0.0))
        if sequential + combinational <= 0:
            continue
        profile = {
            "sequential": sequential,
            "combinational": combinational,
            "activity": activity,
        }
        if directory.name == TROJAN_FIXTURE:
            trojan = profile
        else:
            clean.append(profile)

    if not clean or trojan is None:
        raise GeneratorError(
            "cannot read clean and trojan metric profiles from "
            f"{TRACE_PROVENANCE_ROOT}"
        )

    averaged = {
        key: sum(row[key] for row in clean) / len(clean) for key in clean[0]
    }
    return averaged, trojan


def metrics_from_profile(
    rng: np.random.Generator,
    profile: dict[str, float],
) -> dict[str, object]:
    """Return a Yosys-shaped metrics mapping jittered around a profile."""
    sequential = max(1, int(round(profile["sequential"] * rng.normal(1.0, METRIC_JITTER))))
    combinational = max(
        1, int(round(profile["combinational"] * rng.normal(1.0, METRIC_JITTER)))
    )
    cells = sequential + combinational
    activity = max(float(cells), profile["activity"] * rng.normal(1.0, METRIC_JITTER))
    wire_bits = max(0, int(round((activity - cells) * 4.0)))

    return {
        "cell_types": {"$dff": sequential, "$and": combinational},
        "cells": cells,
        "wire_bits": wire_bits,
    }


def design_evidence_from_metrics(
    metrics: dict[str, object],
    label: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    """Return a yosys/verilator evidence mapping matching the metrics used for the trace.

    At run time cell_count_log and the structural ratios are derived by extract_design from
    the same `yosys stat -json` that produced the trace. Drawing them independently would
    make a corpus row describe two different designs.
    """
    cell_types = dict(metrics["cell_types"])  # type: ignore[arg-type]
    sequential = int(cell_types["$dff"])
    combinational = int(cell_types["$and"])
    cells = int(metrics["cells"])  # type: ignore[arg-type]
    wire_bits = int(metrics["wire_bits"])  # type: ignore[arg-type]
    wires = max(1, int(round(wire_bits / 4.0)))

    # Yosys emits one entry per distinct cell type. The reference netlist uses several
    # ($eq, $adffe, $mux, $logic_and, ...) and the Trojan netlist more. A constant here
    # would give the column zero IQR, and the normalizer would then amplify any real
    # fixture value without bound.
    distinct_cell_types = max(
        2, int(round(2.0 + 0.55 * math.sqrt(combinational) * rng.normal(1.0, 0.25)))
    )

    return {
        "yosys": {
            "cell_count": cells,
            "wire_count": wires,
            "wire_bit_count": wire_bits,
            "public_wire_count": max(
                1, int(round(wires * float(rng.uniform(0.10, 0.45))))
            ),
            # Present in most rows. At 25% presence both quartiles were zero, so the
            # column had zero IQR and the normalizer would amplify any real value.
            "memory_bit_count": (
                int(round(rng.exponential(64.0))) if rng.random() < 0.60 else 0
            ),
            "cell_type_count": distinct_cell_types,
            "sequential_cells": sequential,
            "combinational_cells": combinational,
            "netlist_delta_ratio": float(
                rng.beta(2.0, 8.0) if label == 1 else rng.beta(1.0, 24.0)
            ),
        },
        "verilator": {
            "assertion_count": 64,
            "failed_assertions": int(
                round(64 * (rng.beta(2.0, 8.0) if label == 1 else rng.beta(1.0, 24.0)))
            ),
        },
    }


def synthesise_traces(
    rng: np.random.Generator,
    label: int,
    profiles: tuple[dict[str, float], dict[str, float]],
) -> dict[str, list[float]]:
    """Return power, EM and timing traces from the production synthesiser."""
    from app.hardware.chipwhisperer.synthesis_trace import generate_samples

    clean_profile, trojan_profile = profiles
    metrics = metrics_from_profile(rng, trojan_profile if label == 1 else clean_profile)
    synthesise_traces.last_metrics = metrics  # type: ignore[attr-defined]
    device_seed = hashlib.sha256(
        rng.integers(0, 2**63 - 1, dtype=np.int64).tobytes()
    ).hexdigest()[:16]

    return {
        f"{channel}_trace": generate_samples(
            metrics=metrics,
            device_seed=device_seed,
            channel=channel,
            samples=TRACE_LENGTH,
        )
        for channel in ("power", "em", "timing")
    }


def draw_bounded(
    rng: np.random.Generator,
    size: int,
    elevated: bool,
    coverage_fraction: float,
) -> np.ndarray:
    """Draw a [0,1] feature: a realistic low-mean bulk plus a uniform coverage tail.

    The fixtures sit low (netlist_delta_ratio 0.0 clean against 0.18 for the Trojan), so
    the bulk is Beta(1,24) or Beta(2,8). The uniform tail keeps the fitted support
    spanning the whole interval a clamped extractor could emit.
    """
    if elevated:
        bulk = rng.beta(2.0, 8.0, size)
    else:
        bulk = rng.beta(1.0, 24.0, size)

    tail = rng.uniform(0.0, 1.0, size)
    use_tail = rng.random(size) < coverage_fraction
    return np.where(use_tail, tail, bulk)


def build_dataset_from_traces(
    *,
    feature_names: tuple[str, ...],
    samples: int,
    seed: int,
    class_weights: tuple[float, ...],
    trojan_names: tuple[str, ...],
    supply_names: tuple[str, ...],
    trojan_effect: float,
    label_noise: float,
    coverage_fraction: float,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[str, ...],
    dict[str, dict[str, float]],
]:
    """Generate the corpus with physical features produced by extract_physical."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from app.ai.feature_extraction.design_features import extract_design
    from app.ai.feature_extraction.physical_features import extract_physical

    design_names: set[str] = set()
    rng = np.random.default_rng(seed)
    labels = rng.choice(len(class_weights), size=samples, p=class_weights)
    profiles = read_metric_profiles()

    probe = extract_physical(synthesise_traces(rng, 0, profiles), SEQUENCE_LENGTH)[0]
    physical_names = tuple(sorted(probe))
    derived = tuple(name for name in feature_names if name in probe)
    bounded_names = tuple(name for name in feature_names if name not in probe)

    features = np.zeros((samples, len(feature_names)), dtype=np.float64)
    sequences = np.zeros(
        (samples, SEQUENCE_LENGTH, SEQUENCE_CHANNELS), dtype=np.float32
    )
    index_of = {name: position for position, name in enumerate(feature_names)}

    for row, label in enumerate(labels):
        values, sequence = extract_physical(
            synthesise_traces(rng, int(label), profiles), SEQUENCE_LENGTH
        )
        for name in derived:
            features[row, index_of[name]] = values[name]
        sequences[row] = sequence

        design = extract_design(
            design_evidence_from_metrics(
                synthesise_traces.last_metrics,  # type: ignore[attr-defined]
                int(label),
                rng,
            )
        )
        for name, value in design.items():
            if name in index_of:
                features[row, index_of[name]] = value
                design_names.add(name)

    for name in bounded_names:
        if name in design_names:
            continue
        column = index_of[name]
        elevated = np.zeros(samples, dtype=bool)
        if name in trojan_names:
            elevated |= labels == 1
        if name in supply_names:
            elevated |= labels == 2

        drawn = np.empty(samples, dtype=np.float64)
        if elevated.any():
            drawn[elevated] = draw_bounded(
                rng, int(elevated.sum()), True, coverage_fraction
            )
        if (~elevated).any():
            drawn[~elevated] = draw_bounded(
                rng, int((~elevated).sum()), False, coverage_fraction
            )
        features[:, column] = drawn

    if label_noise > 0.0:
        flip = rng.random(samples) < label_noise
        if flip.any():
            labels[flip] = rng.choice(len(class_weights), size=int(flip.sum()))

    return (
        features,
        sequences,
        labels.astype(np.int64),
        physical_names,
        {"clean": profiles[0], "trojan": profiles[1]},
    )


def write_outputs(
    output: Path,
    features: np.ndarray,
    sequences: np.ndarray,
    labels: np.ndarray,
    manifest: dict,
) -> tuple[Path, str]:
    """Write the compressed archive and its lineage manifest, returning the digest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        features=features,
        sequences=sequences,
        labels=labels,
    )

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest["dataset_sha256"] = digest

    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the synthetic semiconductor training corpus by feature name.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--schema-attr",
        default="FEATURE_NAMES",
        help="tuple name in app.ai.feature_extraction.schemas (default: FEATURE_NAMES)",
    )
    parser.add_argument(
        "--features",
        default=None,
        help="explicit comma-separated feature names, overrides --schema-attr",
    )
    parser.add_argument(
        "--trojan-features",
        choices=("legacy", "extended"),
        default="legacy",
        help="legacy reproduces the original index set; extended adds simulation_failure_ratio",
    )
    parser.add_argument(
        "--trojan-effect",
        type=float,
        default=2.0,
        help="mean shift in sigma applied to trojan discriminators (default: 2.0, legacy)",
    )
    parser.add_argument(
        "--supply-effect",
        type=float,
        default=2.2,
        help="mean shift in sigma applied to supply-chain discriminators (default: 2.2)",
    )
    parser.add_argument(
        "--label-noise",
        type=float,
        default=0.0,
        help="fraction of labels randomly reassigned after generation (default: 0.0)",
    )
    parser.add_argument(
        "--physical-source",
        choices=("extractor", "raw"),
        default="extractor",
        help="extractor synthesises traces and calls extract_physical (default); "
             "raw reproduces the legacy N(0,1) draw for every feature",
    )
    parser.add_argument(
        "--coverage-fraction",
        type=float,
        default=0.15,
        help="fraction of bounded features drawn uniformly over [0,1] for support coverage",
    )
    parser.add_argument(
        "--exclude-boost",
        default="",
        help="comma-separated feature names to leave unboosted, for ablation studies",
    )
    args = parser.parse_args()

    if args.samples < 1:
        print("FAIL: --samples must be positive", file=sys.stderr)
        return 2
    if not 0.0 <= args.label_noise < 1.0:
        print("FAIL: --label-noise must be in [0.0, 1.0)", file=sys.stderr)
        return 2

    excluded = frozenset(
        part.strip() for part in args.exclude_boost.split(",") if part.strip()
    )

    try:
        schema_label, feature_names = resolve_feature_names(
            args.schema_attr, args.features
        )

        if len(set(feature_names)) != len(feature_names):
            raise GeneratorError("selected schema contains duplicate feature names")

        trojan_source = (
            TROJAN_FEATURES_LEGACY
            if args.trojan_features == "legacy"
            else TROJAN_FEATURES_EXTENDED
        )

        trojan_indices, trojan_applied, trojan_absent = select_boost_indices(
            feature_names, trojan_source, excluded, "trojan"
        )
        supply_indices, supply_applied, supply_absent = select_boost_indices(
            feature_names, SUPPLY_CHAIN_FEATURES, excluded, "supply-chain"
        )
    except GeneratorError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    physical_names: tuple[str, ...] = ()
    metric_profiles: dict[str, dict[str, float]] = {}

    if args.physical_source == "extractor":
        (
            features,
            sequences,
            labels,
            physical_names,
            metric_profiles,
        ) = build_dataset_from_traces(
            feature_names=feature_names,
            samples=args.samples,
            seed=args.seed,
            class_weights=DEFAULT_CLASS_WEIGHTS,
            trojan_names=tuple(trojan_applied),
            supply_names=tuple(supply_applied),
            trojan_effect=args.trojan_effect,
            label_noise=args.label_noise,
            coverage_fraction=args.coverage_fraction,
        )
    else:
        features, sequences, labels = build_dataset(
            feature_names=feature_names,
            samples=args.samples,
            seed=args.seed,
            class_weights=DEFAULT_CLASS_WEIGHTS,
            trojan_indices=trojan_indices,
            supply_indices=supply_indices,
            trojan_effect=args.trojan_effect,
            supply_effect=args.supply_effect,
            label_noise=args.label_noise,
        )

    counts = np.bincount(labels, minlength=len(CLASS_LABELS)).tolist()

    manifest = {
        "generator": "scripts/ai/generate_synthetic_dataset.py",
        "schema": schema_label,
        "feature_count": len(feature_names),
        "feature_names": list(feature_names),
        "samples": int(args.samples),
        "seed": int(args.seed),
        "sequence_length": SEQUENCE_LENGTH,
        "sequence_channels": SEQUENCE_CHANNELS,
        "class_labels": list(CLASS_LABELS),
        "class_weights": list(DEFAULT_CLASS_WEIGHTS),
        "class_counts": counts,
        "trojan_feature_set": args.trojan_features,
        "trojan_effect_sigma": (
            float(args.trojan_effect) if args.physical_source == "raw" else None
        ),
        "trojan_effect_sigma_note": (
            "null in extractor mode: no sigma shift is applied to any column. Physical "
            "features come from extract_physical over synthesised traces, design features "
            "from extract_design over the same netlist metrics. Class separation derives "
            "from the 8-cell reference against the 27-cell controlled Trojan."
        ),
        "trojan_features_applied": (
            trojan_applied if args.physical_source == "raw" else []
        ),
        "trojan_features_absent_from_schema": trojan_absent,
        "supply_effect_sigma": float(args.supply_effect),
        "supply_features_applied": supply_applied,
        "supply_features_absent_from_schema": supply_absent,
        "excluded_from_boost": sorted(excluded),
        "label_noise": float(args.label_noise),
        "physical_source": args.physical_source,
        "physical_features_from_extractor": sorted(physical_names),
        "coverage_fraction": float(args.coverage_fraction),
        "trace_length": TRACE_LENGTH,
        "trace_synthesiser": "app/hardware/chipwhisperer/synthesis_trace.py",
        "trace_metric_profiles": metric_profiles,
        "trace_metric_jitter": METRIC_JITTER,
        "trace_parameter_source": (
            "sequential_cells, combinational_cells and activity_proxy read from the "
            "provenance blocks of hardware_lab/chipwhisperer/reference_traces; corpus "
            "traces are produced by the same generate_samples() that produced the "
            "fixture traces, from the same kind of Yosys metrics"
        ),
        "separability_note": (
            "In raw mode, classes are separated by explicit mean shifts on the named "
            "features above. In extractor mode there are no mean shifts: separation "
            "derives from two netlist profiles, the 8-cell reference and the 27-cell "
            "controlled Trojan, propagated through the production trace synthesiser and "
            "the production feature extractors. Either way this is a two-design synthetic "
            "corpus. Any classification metric obtained on it measures separability "
            "between those two designs, not detector performance on real silicon."
        ),
    }

    output = Path(args.output).expanduser()
    manifest_path, digest = write_outputs(
        output, features, sequences, labels, manifest
    )

    print(f"schema            : {schema_label} ({len(feature_names)} features)")
    print(f"samples           : {args.samples}  class counts: {counts}")
    if args.physical_source == "raw":
        print(f"trojan boost      : {args.trojan_effect}s on {trojan_applied}")
    else:
        print("trojan signal     : netlist profile 8 cells -> 27 cells, no sigma shift")
    if trojan_absent:
        print(f"  absent from schema: {trojan_absent}")
    print(f"supply boost      : {args.supply_effect}s on {supply_applied}")
    if supply_absent:
        print(f"  absent from schema: {supply_absent}")
    if excluded:
        print(f"excluded from boost: {sorted(excluded)}")
    if args.label_noise:
        print(f"label noise       : {args.label_noise}")
    print(f"features          : {features.shape}")
    print(f"sequences         : {sequences.shape}")
    print(f"output            : {output}")
    print(f"manifest          : {manifest_path}")
    print(f"dataset_sha256    : {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
