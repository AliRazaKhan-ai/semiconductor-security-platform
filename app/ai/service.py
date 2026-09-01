"""End-to-end production AI pipeline facade."""
from __future__ import annotations

from typing import Any

from app.ai.feature_extraction import FeatureExtractionService
from app.ai.feature_extraction.normalization import RobustNormalizer


class AIPipelineService:
 def __init__(self,feature_service:FeatureExtractionService,normalizer:RobustNormalizer,cnn,anomaly,risk): self.features=feature_service; self.normalizer=normalizer; self.cnn=cnn; self.anomaly=anomaly; self.risk=risk
 def analyze(self,evidence:dict[str,Any],controls:dict[str,Any]):
  fv=self.features.extract(evidence); x=self.normalizer.transform(fv.to_array()); cnn=self.cnn.infer(fv.sequence_array()); ae=self.anomaly.infer(x); decision=self.risk.decide(x,cnn,ae,controls,float(evidence.get("evidence_quality",1.0)))
  return {"feature_vector":fv.to_dict(),"tensorflow":cnn.to_dict(),"pytorch":ae.to_dict(),"decision":decision.to_dict()}
