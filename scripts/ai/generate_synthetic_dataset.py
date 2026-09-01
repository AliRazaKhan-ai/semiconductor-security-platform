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
        "trojan_effect_sigma": float(args.trojan_effect),
        "trojan_features_applied": trojan_applied,
        "trojan_features_absent_from_schema": trojan_absent,
        "supply_effect_sigma": float(args.supply_effect),
        "supply_features_applied": supply_applied,
        "supply_features_absent_from_schema": supply_absent,
        "excluded_from_boost": sorted(excluded),
        "label_noise": float(args.label_noise),
        "separability_note": (
            "Classes are separated by explicit mean shifts on the named features above. "
            "Any classification metric obtained on this corpus measures the generator's "
            "designed separability, not detector performance on real silicon."
        ),
    }

    output = Path(args.output).expanduser()
    manifest_path, digest = write_outputs(
        output, features, sequences, labels, manifest
    )

    print(f"schema            : {schema_label} ({len(feature_names)} features)")
    print(f"samples           : {args.samples}  class counts: {counts}")
    print(f"trojan boost      : {args.trojan_effect}s on {trojan_applied}")
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
