"""Scikit-learn risk engine with model fusion, classification, and confidence."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from app.ai.common import AIDecision, ModelOutput, canonical_hash
from .model import load_risk_model,predict_risk
from .calibration import confidence_score,risk_level
from .policy_fusion import fuse
from .explanation import explain
class RiskEngineService:
 def __init__(self,model_path:Path,feature_names:tuple[str,...],version:str="1.0.0",expected_hash:str|None=None): self.path=model_path; self.names=feature_names; self.version=version; self.expected_hash=expected_hash; self._model=None
 def decide(self,features:np.ndarray,cnn:ModelOutput,anomaly:ModelOutput,controls:dict,evidence_quality:float=1.0)->AIDecision:
  if self._model is None:self._model=load_risk_model(self.path,self.expected_hash)
  risk_input=np.concatenate([np.asarray(features,dtype=np.float32),[cnn.score,cnn.confidence,anomaly.score,anomaly.confidence]])
  base=predict_risk(self._model,risk_input); final,reasons=fuse(base,cnn.score,anomaly.score,controls); level=risk_level(final)
  if cnn.label not in ("CLEAN","INDETERMINATE"): reasons.append(f"CNN classification: {cnn.label}")
  if anomaly.label=="ANOMALOUS": reasons.append("autoencoder detected an unknown-pattern anomaly")
  confidence=confidence_score(cnn.confidence,anomaly.confidence,final,evidence_quality)
  classification="COMPROMISED" if final>=.65 else "SUSPICIOUS" if final>=.35 else "CLEAN"
  recommendation="BLOCK" if final>=.65 else "MANUAL_REVIEW" if final>=.35 else "PROCEED_TO_COMPLIANCE"
  explanation=explain(self._model,tuple(self.names)+( "cnn_score","cnn_confidence","anomaly_score","anomaly_confidence"),risk_input)
  outputs={"tensorflow":cnn.to_dict(),"pytorch":anomaly.to_dict(),"risk_model":{"version":self.version,"base_probability":base,"explanation":explanation}}
  return AIDecision(classification,final,confidence,level,recommendation,tuple(dict.fromkeys(reasons)),outputs,canonical_hash(list(map(float,features))))
