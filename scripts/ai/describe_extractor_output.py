"""Purpose: Report what extract_physical produces for the real fixture traces.
Directory: scripts/ai.
Dependencies: numpy; app.ai.feature_extraction.physical_features.
Connection: Read-only diagnostic establishing the target distribution the Phase 3B
corpus generator must cover. Writes nothing and changes no state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.feature_extraction.physical_features import extract_physical  # noqa: E402

TRACE_ROOT = ROOT / "hardware_lab" / "chipwhisperer" / "reference_traces"
CORPUS = ROOT / "data" / "training" / "semiconductor_ai_v21.npz"
MANIFEST = CORPUS.with_suffix(".manifest.json")

CHANNELS = {
    "power_trace": "side_channel_trace.json",
    "em_trace": "ai_em_trace.json",
    "timing_trace": "ai_timing_trace.json",
}


def numeric_series(payload: object, depth: int = 0) -> list[float] | None:
    """Return the first numeric array found anywhere in a decoded JSON document."""
    if depth > 6:
        return None

    if isinstance(payload, list):
        if len(payload) >= 16 and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in payload
        ):
            return [float(item) for item in payload]
        for item in payload:
            found = numeric_series(item, depth + 1)
            if found is not None:
                return found
        return None

    if isinstance(payload, dict):
        for key in ("samples", "trace", "values", "data", "series", "points"):
            if key in payload:
                found = numeric_series(payload[key], depth + 1)
                if found is not None:
                    return found
        for value in payload.values():
            found = numeric_series(value, depth + 1)
            if found is not None:
                return found

    return None


def load_channels(directory: Path) -> dict[str, list[float]] | None:
    evidence: dict[str, list[float]] = {}
    for channel, filename in CHANNELS.items():
        path = directory / filename
        if not path.is_file():
            print(f"  MISSING {filename}")
            return None
        series = numeric_series(json.loads(path.read_text(encoding="utf-8")))
        if series is None:
            print(f"  NO NUMERIC SERIES in {filename}")
            return None
        evidence[channel] = series
    return evidence


def main() -> int:
    if not TRACE_ROOT.is_dir():
        print(f"Trace root not found: {TRACE_ROOT}")
        return 1

    corpus_min = corpus_max = None
    names: list[str] = []
    if CORPUS.is_file() and MANIFEST.is_file():
        matrix = np.load(CORPUS, allow_pickle=False)["features"].astype(float)
        names = list(json.loads(MANIFEST.read_text(encoding="utf-8"))["feature_names"])
        corpus_min = matrix.min(axis=0)
        corpus_max = matrix.max(axis=0)

    extracted: dict[str, dict[str, float]] = {}

    for directory in sorted(p for p in TRACE_ROOT.iterdir() if p.is_dir()):
        print(f"=== {directory.name} ===")
        evidence = load_channels(directory)
        if evidence is None:
            print()
            continue

        for channel, series in evidence.items():
            array = np.asarray(series, dtype=float)
            print(f"  {channel:14} n={array.size:5d} mean={array.mean():12.6f} "
                  f"std={array.std():10.6f} min={array.min():10.4f} "
                  f"max={array.max():10.4f}")

        try:
            features, sequence = extract_physical(evidence, 256)
        except Exception as error:  # noqa: BLE001 - diagnostic must report, not raise
            print(f"  extract_physical FAILED: {type(error).__name__}: {error}")
            print()
            continue

        extracted[directory.name] = features
        print(f"  sequence: {sequence.shape}")
        print()

    if not extracted:
        print("No fixture produced physical features.")
        return 1

    print("=== extract_physical output vs corpus range ===")
    header = f"{'feature':26} {'fixture_min':>13} {'fixture_max':>13}"
    if corpus_min is not None:
        header += f" {'corpus_min':>11} {'corpus_max':>11}  covered"
    print(header)

    feature_names = sorted(next(iter(extracted.values())).keys())
    outside: list[str] = []

    for name in feature_names:
        values = [row[name] for row in extracted.values()]
        line = f"{name:26} {min(values):13.4f} {max(values):13.4f}"
        if corpus_min is not None and name in names:
            index = names.index(name)
            low, high = corpus_min[index], corpus_max[index]
            covered = low <= min(values) and max(values) <= high
            line += f" {low:11.4f} {high:11.4f}  {'yes' if covered else 'NO'}"
            if not covered:
                outside.append(name)
        print(line)

    if outside:
        print()
        print(f"OUTSIDE the corpus range ({len(outside)}): {outside}")
        print("These are the features the trained models have never seen.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
