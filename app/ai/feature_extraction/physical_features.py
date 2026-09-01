"""Numerically stable extraction of side-channel power, EM, and timing features."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.ai.common import AIFeatureError


def _array(value: Any, name: str) -> np.ndarray:
    a=np.asarray(value, dtype=np.float64).reshape(-1)
    if a.size < 16: raise AIFeatureError(f"{name} requires at least 16 samples")
    if not np.all(np.isfinite(a)): raise AIFeatureError(f"{name} contains non-finite values")
    return a

def _entropy(a: np.ndarray) -> float:
    spectrum=np.abs(np.fft.rfft(a-a.mean()))**2
    total=float(spectrum.sum())
    if total <= 1e-15: return 0.0
    p=spectrum/total
    p=p[p>0]
    return float(-(p*np.log2(p)).sum()/max(1.0, math.log2(len(spectrum))))

def _moments(a: np.ndarray) -> tuple[float,float]:
    centered=a-a.mean(); std=float(a.std())
    if std <= 1e-12: return 0.0, 0.0
    return float(np.mean((centered/std)**3)), float(np.mean((centered/std)**4)-3.0)

def describe(a: np.ndarray, prefix: str) -> dict[str,float]:
    rms=float(np.sqrt(np.mean(a*a))); p2p=float(np.ptp(a)); skew,kurt=_moments(a)
    return {f"{prefix}_mean":float(a.mean()),f"{prefix}_std":float(a.std()),f"{prefix}_rms":rms,
            f"{prefix}_peak_to_peak":p2p,f"{prefix}_crest_factor":float(np.max(np.abs(a))/(rms+1e-12)),
            f"{prefix}_skewness":skew,f"{prefix}_kurtosis":kurt,f"{prefix}_spectral_entropy":_entropy(a)}

def resample(a: np.ndarray, length: int) -> np.ndarray:
    if length < 16: raise AIFeatureError("sequence length must be at least 16")
    x=np.linspace(0.0,1.0,a.size); target=np.linspace(0.0,1.0,length)
    return np.interp(target,x,a)

def extract_physical(evidence: dict[str,Any], sequence_length: int=256) -> tuple[dict[str,float], np.ndarray]:
    power=_array(evidence.get("power_trace"),"power_trace")
    em=_array(evidence.get("em_trace"),"em_trace")
    timing=_array(evidence.get("timing_trace"),"timing_trace")
    p=describe(power,"power"); e=describe(em,"em")
    timing_mean=float(timing.mean()); timing_std=float(timing.std())
    features={**p,"em_mean":e["em_mean"],"em_std":e["em_std"],"em_rms":e["em_rms"],
              "em_peak_to_peak":e["em_peak_to_peak"],"em_spectral_entropy":e["em_spectral_entropy"],
              "timing_mean":timing_mean,"timing_std":timing_std,
              "timing_jitter":float(np.mean(np.abs(np.diff(timing)))/(abs(timing_mean)+1e-12))}
    seq=np.stack([resample(power,sequence_length),resample(em,sequence_length),resample(timing,sequence_length)],axis=-1)
    means=seq.mean(axis=0); stds=seq.std(axis=0); seq=(seq-means)/(stds+1e-8)
    return features, seq.astype(np.float32)
