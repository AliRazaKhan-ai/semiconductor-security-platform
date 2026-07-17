"""Shared immutable AI contracts, hashing, and numeric validation."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable

class AIError(RuntimeError):
    code = "ai_error"

class AIConfigurationError(AIError):
    code = "ai_configuration_error"

class AIModelError(AIError):
    code = "ai_model_error"

class AIFeatureError(AIError):
    code = "ai_feature_error"


def canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def finite_float(value: Any, name: str) -> float:
    import math
    try: result=float(value)
    except (TypeError, ValueError) as exc: raise AIFeatureError(f"{name} must be numeric") from exc
    if not math.isfinite(result): raise AIFeatureError(f"{name} must be finite")
    return result

def clamp(value: float, low: float=0.0, high: float=1.0) -> float:
    return max(low, min(high, float(value)))

@dataclass(frozen=True, slots=True)
class ModelOutput:
    model_name: str
    model_version: str
    label: str
    score: float
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    explanation: dict[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True, slots=True)
class AIDecision:
    classification: str
    risk_score: float
    confidence_score: float
    risk_level: str
    deployment_recommendation: str
    reasons: tuple[str, ...]
    model_outputs: dict[str, dict[str, Any]]
    feature_hash: str
    def to_dict(self) -> dict[str, Any]: return asdict(self)
