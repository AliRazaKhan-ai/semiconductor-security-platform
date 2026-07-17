"""Convert CNN probabilities into calibrated label, confidence, and uncertainty."""
from __future__ import annotations
import math
import numpy as np
from app.ai.common import clamp

def postprocess(probabilities: np.ndarray, labels: tuple[str,...], min_confidence: float=.60)->dict:
    if len(labels)!=len(probabilities): raise ValueError("label count mismatch")
    idx=int(np.argmax(probabilities)); top=float(probabilities[idx]); ordered=np.sort(probabilities); margin=float(ordered[-1]-ordered[-2])
    entropy=float(-sum(p*math.log(max(p,1e-12)) for p in probabilities)/math.log(len(probabilities)))
    confidence=clamp(.55*top+.30*margin+.15*(1-entropy))
    label=labels[idx] if confidence>=min_confidence else "INDETERMINATE"
    return {"label":label,"score":top,"confidence":confidence,"probabilities":{k:float(v) for k,v in zip(labels,probabilities)},"entropy":entropy,"margin":margin}
