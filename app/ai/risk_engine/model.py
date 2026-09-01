"""Integrity-checked Scikit-learn risk-model loading and probability inference."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import joblib
import numpy as np

from app.ai.common import AIModelError


def _hash(path:Path)->str:
 h=sha256(); h.update(path.read_bytes()); return h.hexdigest()
def load_risk_model(path:Path,expected_hash:str|None=None):
 if not path.is_file(): raise AIModelError(f"risk model not found: {path}")
 if expected_hash and _hash(path)!=expected_hash: raise AIModelError("risk model integrity verification failed")
 return joblib.load(path)
def predict_risk(model,x:np.ndarray)->float:
 if not hasattr(model,"predict_proba"): raise AIModelError("risk model must support predict_proba")
 p=np.asarray(model.predict_proba(np.asarray(x,dtype=np.float32).reshape(1,-1)),dtype=float)[0]
 return float(p[-1])
