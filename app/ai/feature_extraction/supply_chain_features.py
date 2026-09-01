"""Extract policy-bounded supplier, provenance, PUF, and root-of-trust features."""
from __future__ import annotations

from typing import Any

from app.ai.common import clamp, finite_float


def extract_supply_chain(evidence: dict[str,Any]) -> dict[str,float]:
    s=dict(evidence.get("supply_chain",{})); p=dict(evidence.get("puf",{})); o=dict(evidence.get("opentitan",{}))
    custody=max(1.0,finite_float(s.get("custody_event_count",1),"custody_event_count"))
    return {
      "supplier_risk":clamp(finite_float(s.get("supplier_risk",0),"supplier_risk")),
      "country_risk":clamp(finite_float(s.get("country_risk",0),"country_risk")),
      "custody_gap_ratio":clamp(finite_float(s.get("custody_gap_count",0),"custody_gap_count")/custody),
      "certificate_risk":0.0 if bool(s.get("certificate_valid",True)) else 1.0,
      "sbom_mismatch_ratio":clamp(finite_float(s.get("sbom_mismatch_ratio",0),"sbom_mismatch_ratio")),
      "threat_intel_score":clamp(finite_float(s.get("threat_intel_score",0),"threat_intel_score")),
      "puf_instability":clamp(1.0-finite_float(p.get("stability_score",1),"stability_score")),
      "opentitan_risk":0.0 if bool(o.get("verified",True)) else 1.0 }
