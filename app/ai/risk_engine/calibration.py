"""Confidence and ordinal risk-level calibration."""
from __future__ import annotations

from app.ai.common import clamp


def risk_level(score:float)->str:
 return "CRITICAL" if score>=.85 else "HIGH" if score>=.65 else "MEDIUM" if score>=.35 else "LOW"
def confidence_score(tf_conf:float,ae_conf:float,risk_probability:float,evidence_quality:float)->float:
 separation=abs(risk_probability-.5)*2
 return clamp(.30*tf_conf+.25*ae_conf+.25*separation+.20*evidence_quality)
