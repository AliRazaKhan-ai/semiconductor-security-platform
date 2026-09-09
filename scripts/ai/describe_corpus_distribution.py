"""Purpose: Describe the training corpus distribution and compare it to the fitted normalizer.
Directory: scripts/ai.
Dependencies: numpy, json, pathlib.
Connection: Read-only diagnostic for the Phase 3 feature-distribution contract.
Writes nothing and imports no application module.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / "data" / "training"
NORMALIZER = ROOT / "models" / "manifests" / "feature_normalizer.json"


def load_normalizer() -> tuple[list[str], np.ndarray, np.ndarray]:
    payload = json.loads(NORMALIZER.read_text(encoding="utf-8"))
    return (
        list(payload["feature_names"]),
        np.asarray(payload["median"], dtype=float),
        np.asarray(payload["scale"], dtype=float),
    )


def main() -> int:
    names, median, scale = load_normalizer()
    print(f"Normalizer: {len(names)} features")
    print(f"  scale  min={scale.min():.4f} max={scale.max():.4f} "
          f"mean={scale.mean():.4f}")
    print(f"  median min={median.min():.4f} max={median.max():.4f}")
    print("  IQR of a standard normal distribution = 1.3490")
    print()

    archives = sorted(TRAINING.glob("*.npz"))
    if not archives:
        print("No .npz archives found under data/training")
        return 1

    for archive in archives:
        print(f"=== {archive.name} ===")
        data = np.load(archive, allow_pickle=False)
        for key in data.files:
            print(f"  {key}: shape={data[key].shape} dtype={data[key].dtype}")

        matrix = None
        for key in data.files:
            candidate = data[key]
            if candidate.ndim == 2 and candidate.shape[1] == len(names):
                matrix = candidate.astype(float)
                print(f"  -> feature matrix: '{key}'")
                break

        if matrix is None:
            print("  (no array matches the normalizer feature count)")
            print()
            continue

        q25 = np.percentile(matrix, 25, axis=0)
        q50 = np.percentile(matrix, 50, axis=0)
        q75 = np.percentile(matrix, 75, axis=0)
        iqr = q75 - q25

        print()
        print(f"  {'feature':28} {'min':>10} {'median':>10} {'max':>10} "
              f"{'IQR':>8} {'fit_med':>9} {'fit_scale':>9}")
        for index, name in enumerate(names):
            column = matrix[:, index]
            print(f"  {name:28} {column.min():10.4f} {q50[index]:10.4f} "
                  f"{column.max():10.4f} {iqr[index]:8.4f} "
                  f"{median[index]:9.4f} {scale[index]:9.4f}")

        median_delta = np.abs(q50 - median)
        scale_delta = np.abs(iqr - scale)
        print()
        print(f"  |corpus median - fitted median|: max={median_delta.max():.6f}")
        print(f"  |corpus IQR    - fitted scale| : max={scale_delta.max():.6f}")
        print("  (both near zero => the normalizer was fitted on this corpus)")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
