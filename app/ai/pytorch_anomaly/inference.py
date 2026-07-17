"""Compute per-feature reconstruction errors using inference-only PyTorch execution."""
from __future__ import annotations
import numpy as np
from app.ai.common import AIModelError
def reconstruction_error(model,features:np.ndarray)->tuple[float,np.ndarray]:
    try: import torch
    except ImportError as exc: raise AIModelError("PyTorch is not installed") from exc
    x=torch.as_tensor(np.asarray(features,dtype=np.float32).reshape(1,-1))
    with torch.inference_mode(): reconstructed=model(x)
    errors=((reconstructed-x)**2).cpu().numpy().reshape(-1)
    return float(errors.mean()),errors
