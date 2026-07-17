"""Production TensorFlow CNN classifier facade."""
from __future__ import annotations
from pathlib import Path
from app.ai.common import ModelOutput, canonical_hash
from .loader import load_model
from .inference import predict
from .postprocessing import postprocess
class TensorFlowClassifierService:
    def __init__(self,model_path:Path,labels:tuple[str,...],version:str="1.0.0",expected_hash:str|None=None,min_confidence:float=.60):
        self.model_path=model_path; self.labels=labels; self.version=version; self.expected_hash=expected_hash; self.min_confidence=min_confidence; self._model=None
    def infer(self,sequence):
        if self._model is None: self._model=load_model(self.model_path,self.expected_hash)
        result=postprocess(predict(self._model,sequence),self.labels,self.min_confidence)
        return ModelOutput("tensorflow_cnn",self.version,result["label"],result["score"],result["confidence"],result["probabilities"],{"entropy":result["entropy"],"margin":result["margin"]},canonical_hash(result))
