"""Production PyTorch anomaly detector facade."""
from __future__ import annotations
from pathlib import Path
from app.ai.common import ModelOutput, canonical_hash
from .loader import load_autoencoder
from .inference import reconstruction_error
from .postprocessing import postprocess
class PyTorchAnomalyService:
    def __init__(self,model_path:Path,feature_names:tuple[str,...],threshold:float,scale:float,version:str="1.0.0",latent_dim:int=8,expected_hash:str|None=None):
        self.model_path=model_path; self.names=feature_names; self.threshold=threshold; self.scale=scale; self.version=version; self.latent_dim=latent_dim; self.expected_hash=expected_hash; self._model=None
    def infer(self,features):
        if self._model is None:self._model=load_autoencoder(self.model_path,len(self.names),self.latent_dim,self.expected_hash)
        error,per=reconstruction_error(self._model,features); r=postprocess(error,per,self.threshold,self.scale,self.names)
        return ModelOutput("pytorch_autoencoder",self.version,r["label"],r["score"],r["confidence"],{"normal":1-r["score"],"anomalous":r["score"]},{"reconstruction_error":error,"threshold":self.threshold,"top_errors":r["top_errors"]},canonical_hash(r))
