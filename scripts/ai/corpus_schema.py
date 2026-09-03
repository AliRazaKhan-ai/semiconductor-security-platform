"""Purpose: Resolve the feature schema a training corpus was generated against.

Directory: scripts/ai
Dependencies: standard library; app.ai.feature_extraction.schemas
Connection: used by train_normalizer, train_pytorch_autoencoder, train_risk_engine and
            generate_model_signals in place of a hardcoded FEATURE_NAMES import

Four training scripts imported FEATURE_NAMES directly: one to fit the normalizer, three to
assert the loaded normalizer matched it. That pinned the entire chain to schema 1.0, so a
corpus generated against any other schema could not be trained on, and the failure appeared
as a shape error inside RobustNormalizer.fit rather than as a schema statement.

The corpus manifest written beside every .npz records the exact feature names used to
generate it, so the corpus now carries its own schema. A model cannot be trained against a
schema the data was not generated for, because no script holds an opinion about which
schema is correct.

Corpora predating the manifest fall back to FEATURE_NAMES, which is what they were in fact
generated against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from app.ai.feature_extraction.schemas import FEATURE_NAMES


class CorpusSchemaError(ValueError):
    """Raised when a corpus and its declared schema disagree."""


def manifest_path(dataset: Path) -> Path:
    """Return the manifest path for a corpus."""
    return Path(dataset).with_suffix(".manifest.json")


def resolve_feature_names(dataset: Path) -> tuple[tuple[str, ...], str]:
    """Return (feature_names, source) for a corpus.

    source is the manifest path when one exists, or "FEATURE_NAMES (no manifest)" for a
    corpus that predates manifest generation.
    """
    path = manifest_path(dataset)

    if not path.exists():
        return FEATURE_NAMES, "FEATURE_NAMES (no manifest)"

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusSchemaError(f"{path} is not valid JSON") from exc

    names = manifest.get("feature_names")

    if not isinstance(names, list) or not names:
        raise CorpusSchemaError(f"{path} declares no feature_names")

    resolved = tuple(str(name) for name in names)

    if len(set(resolved)) != len(resolved):
        raise CorpusSchemaError(f"{path} declares duplicate feature names")

    return resolved, str(path)


def require_matching_normalizer(
    normalizer_names: Sequence[str],
    dataset: Path,
) -> tuple[str, ...]:
    """Verify the normalizer was fitted to this corpus's schema. Returns the names.

    Replaces an equality test against a hardcoded constant. It still fails closed on a
    genuine mismatch; it no longer asserts that one particular schema is the only valid one.
    """
    expected, source = resolve_feature_names(dataset)
    actual = tuple(str(name) for name in normalizer_names)

    if actual != expected:
        raise CorpusSchemaError(
            "normalizer feature schema does not match the corpus schema. "
            f"corpus {Path(dataset).name} declares {len(expected)} features "
            f"via {source}; the normalizer was fitted to {len(actual)}. "
            "Refit the normalizer against this corpus before training."
        )

    return expected
