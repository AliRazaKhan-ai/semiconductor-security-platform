"""Run bounded CNN inference and reject malformed model outputs."""
from __future__ import annotations

import numpy as np

from app.ai.common import AIModelError


def predict(model, sequence: np.ndarray) -> np.ndarray:
    x=np.asarray(sequence,dtype=np.float32)
    if x.ndim!=2 or x.shape[1]!=3: raise AIModelError("CNN input must have shape [samples, 3]")
    raw=np.asarray(model.predict(x[None,...],verbose=0),dtype=np.float64).reshape(-1)
    if raw.size<2 or not np.all(np.isfinite(raw)): raise AIModelError("CNN returned invalid probabilities")
    total=raw.sum()
    if np.any(raw<0) or abs(total-1.0)>1e-3:
        exp=np.exp(raw-np.max(raw)); raw=exp/exp.sum()
    return raw
