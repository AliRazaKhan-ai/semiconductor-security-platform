"""Purpose: Record which model generation is deployed, where it came from, and how to roll back.
Directory: scripts/ai.
Dependencies: json, hashlib, pathlib.
Connection: writes models/registry/index.json. Read by operators, not by the runtime.

RISK / model lifecycle. models/registry/index.json was {"models": []} while every
metrics file already carried dataset_sha256, split_digest and evaluation results, and
models/archive held two earlier generations. Every ingredient for a registry existed;
the index was never written.

This is a record, not a serving mechanism. The runtime loads models by the paths in
configs/application/ai.json and does not consult this file. Promotion here means
recording that a generation is deployed, not switching traffic. Stating that plainly
is better than a registry that implies a pipeline the platform does not have.

    registry.py record     write the deployed generation from the metrics files
    registry.py show       print the index
    registry.py rollback   print the steps to restore an archived generation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = PROJECT_ROOT / "models" / "registry" / "index.json"

ARTEFACTS = {
    "trojan_cnn": ("tensorflow", "trojan_cnn"),
    "anomaly_autoencoder": ("pytorch", "anomaly_autoencoder"),
    "risk_engine": ("sklearn", "risk_engine"),
}

# Criteria a candidate must meet before it is recorded as deployed. They are stated
# rather than enforced: enforcement needs a serving layer the platform does not have.
PROMOTION_CRITERIA = [
    "Trained on a digest-verified split; dataset_sha256 and split_digest must agree "
    "across all three artefacts.",
    "tests/ai/test_train_serve_parity.py passes, so the served threshold is the "
    "trained threshold.",
    "tests/ai/test_train_serve_parity.py distribution checks pass, so the extractor "
    "output falls inside the fitted support.",
    "No regression against the incumbent on the held-out TEST split.",
    "tests/integration/test_complete_module_integration.py passes: the known-good "
    "chip completes all eight stages.",
]


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def collect() -> dict[str, Any]:
    """Read the deployed generation from the metrics files beside each artefact."""
    entries = []
    digests: set[str] = set()
    splits: set[str] = set()

    for name, (framework, stem) in sorted(ARTEFACTS.items()):
        base = PROJECT_ROOT / "models" / framework
        metrics_path = base / f"{stem}.metrics.json"

        if not metrics_path.is_file():
            entries.append({"name": name, "framework": framework,
                            "status": "MISSING", "metrics_path": str(metrics_path)})
            continue

        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

        artefact = next(
            (p for p in sorted(base.glob(f"{stem}.*"))
             if p.suffix not in {".json"}),
            None,
        )

        if metrics.get("dataset_sha256"):
            digests.add(str(metrics["dataset_sha256"]))
        if metrics.get("split_digest"):
            splits.add(str(metrics["split_digest"]))

        entries.append(
            {
                "name": name,
                "framework": framework,
                "status": "DEPLOYED",
                "artefact": str(artefact.relative_to(PROJECT_ROOT)) if artefact else None,
                "artefact_sha256": digest(artefact) if artefact else None,
                "metrics": {
                    k: v for k, v in metrics.items()
                    if not isinstance(v, (dict, list))
                },
            }
        )

    return {
        "schema_version": 2,
        "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": (
            "A record of what is deployed, not a serving mechanism. The runtime loads "
            "models by the paths in configs/application/ai.json and does not read this "
            "file."
        ),
        "lineage": {
            "dataset_sha256": sorted(digests),
            "split_digest": sorted(splits),
            "consistent": len(digests) == 1 and len(splits) == 1,
        },
        "promotion_criteria": PROMOTION_CRITERIA,
        "rollback_targets": sorted(
            p.name for p in (PROJECT_ROOT / "models" / "archive").iterdir()
            if p.is_dir()
        ),
        "models": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "show", "rollback"))
    args = parser.parse_args()

    if args.action == "show":
        if not REGISTRY.is_file():
            print("No registry. Run: registry.py record")
            return 1
        print(REGISTRY.read_text(encoding="utf-8"))
        return 0

    if args.action == "rollback":
        archive = PROJECT_ROOT / "models" / "archive"
        targets = sorted(p.name for p in archive.iterdir() if p.is_dir())
        print("Archived generations:")
        for target in targets:
            print(f"  {target}")
        print()
        print("To restore one, with the platform stopped:")
        print("  sudo systemctl stop semisecure-backend")
        print("  cp -a models/archive/<generation>/* models/")
        print("  python scripts/ai/registry.py record")
        print("  sudo systemctl start semisecure-backend")
        print("  pytest tests/ai -q")
        print()
        print("The artefacts and their metrics move together, so the recorded")
        print("dataset_sha256 and split_digest follow the models being restored.")
        return 0

    index = collect()
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    print(f"recorded {len(index['models'])} models")
    print(f"lineage consistent: {index['lineage']['consistent']}")
    print(f"rollback targets  : {', '.join(index['rollback_targets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
