"""Purpose: Measure how separable the training corpus is, by feature block.

Directory: scripts/ai
Dependencies: numpy, scikit-learn; the .manifest.json written beside the corpus
Connection: diagnostic for the v1.0 -> v2.1 schema migration

A classification metric obtained on a generated corpus measures the generator's designed
separability, not detector performance on silicon. This script reports that separability
explicitly, per feature block, so the two are never confused.

Blocks are resolved by feature NAME from the corpus manifest, so a schema change cannot
silently reassign a block. The design block is the one that matters for the migration: v2.0
substituted absolute Yosys statistics for relative structural deviation and scored 0.4969,
which is chance. v2.1 restores netlist_delta_ratio and simulation_failure_ratio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.model_selection import StratifiedKFold, cross_val_score

SUPPLY_CHAIN_FEATURES = {
    "supplier_risk",
    "country_risk",
    "custody_gap_ratio",
    "certificate_risk",
    "sbom_mismatch_ratio",
    "threat_intel_score",
    "puf_instability",
    "opentitan_risk",
}

PHYSICAL_PREFIXES = ("power_", "em_", "timing_")


def block_of(name: str) -> str:
    if name in SUPPLY_CHAIN_FEATURES:
        return "supply"
    if name.startswith(PHYSICAL_PREFIXES):
        return "physical"
    return "design"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npz", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--target-class", type=int, default=1)
    args = parser.parse_args()

    corpus = Path(args.npz)
    manifest_path = corpus.with_suffix(".manifest.json")

    if not manifest_path.exists():
        print(f"FAIL: no manifest beside {corpus}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [str(name) for name in manifest["feature_names"]]

    data = np.load(corpus, allow_pickle=False)
    features = data["features"]
    labels = data["labels"]

    if features.shape[1] != len(names):
        print(
            f"FAIL: corpus has {features.shape[1]} columns, manifest names {len(names)}",
            file=sys.stderr,
        )
        return 2

    print(f"corpus        : {corpus}")
    print(f"schema        : {manifest['schema']} ({len(names)} features)")
    print(f"samples       : {features.shape[0]}  class counts {np.bincount(labels).tolist()}")
    print(f"seed          : {manifest['seed']}  sha256 {manifest['dataset_sha256'][:16]}...")
    print(f"boosted       : {manifest['trojan_features_applied']}")

    absent = manifest.get("trojan_features_absent_from_schema") or []
    if absent:
        print(f"not in schema : {absent}")

    target = (labels == args.target_class).astype(int)
    folds = StratifiedKFold(5, shuffle=True, random_state=args.seed)

    def forest() -> RandomForestClassifier:
        return RandomForestClassifier(n_estimators=200, random_state=args.seed, n_jobs=-1)

    blocks: dict[str, list[int]] = {"physical": [], "design": [], "supply": []}

    for index, name in enumerate(names):
        blocks[block_of(name)].append(index)

    print(f"\n=== class {args.target_class} vs rest, 5-fold CV ROC-AUC, no tuning ===")

    scores = cross_val_score(forest(), features, target, cv=folds, scoring="roc_auc")
    print(f"  all features ({len(names):>2})        {scores.mean():.4f}  +/- {scores.std():.4f}")

    for block, indices in blocks.items():
        if not indices:
            continue
        scores = cross_val_score(
            forest(), features[:, indices], target, cv=folds, scoring="roc_auc"
        )
        marker = "   <== migration decision" if block == "design" else ""
        print(
            f"  {block:<8} block ({len(indices):>2})      "
            f"{scores.mean():.4f}  +/- {scores.std():.4f}{marker}"
        )

    print(f"\n=== per-feature mutual information vs class {args.target_class} ===")

    information = mutual_info_classif(features, target, random_state=args.seed)

    for value, name in sorted(zip(information, names), reverse=True):
        if value <= 0.0:
            continue
        print(f"  {value:.4f}  {name:<28} [{block_of(name)}]")

    zero = [name for value, name in zip(information, names) if value <= 0.0]
    if zero:
        print(f"\n  zero information ({len(zero)}): {', '.join(sorted(zero))}")

    print(
        "\nThese figures measure the separability this generator was written to produce. "
        "They are not detector performance on real silicon."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
