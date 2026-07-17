"""Fail-closed fusion of learned risk and mandatory security controls."""
from __future__ import annotations
from typing import Any
from app.ai.common import clamp
def fuse(base_risk:float,cnn_score:float,anomaly_score:float,controls:dict[str,Any])->tuple[float,list[str]]:
 reasons=[]; mandatory={"puf_authenticated":controls.get("puf_authenticated",False),"opentitan_verified":controls.get("opentitan_verified",False),"digital_twin_verified":controls.get("digital_twin_verified",False),"compliance_passed":controls.get("compliance_passed",False)}
 failed=[k for k,v in mandatory.items() if not v]
 score=clamp(.45*base_risk+.30*cnn_score+.25*anomaly_score)
 if failed: score=max(score,.95); reasons.extend(f"mandatory control failed: {x}" for x in failed)
 if controls.get("sbom_mismatch",False): score=max(score,.80); reasons.append("SBOM mismatch")
 if controls.get("custody_tampered",False): score=max(score,.90); reasons.append("custody provenance tampering")
 return score,reasons
