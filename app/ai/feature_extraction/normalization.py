"""Persisted robust feature normalization with schema enforcement."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import numpy as np
from app.ai.common import AIFeatureError

@dataclass(frozen=True, slots=True)
class RobustNormalizer:
    feature_names: tuple[str,...]; median: tuple[float,...]; scale: tuple[float,...]
    @classmethod
    def fit(cls, x: np.ndarray, names: tuple[str,...]) -> "RobustNormalizer":
        x=np.asarray(x,dtype=np.float64)
        if x.ndim!=2 or x.shape[1]!=len(names): raise AIFeatureError("normalizer shape does not match feature schema")
        med=np.median(x,axis=0); q1=np.quantile(x,.25,axis=0); q3=np.quantile(x,.75,axis=0); scale=np.where(q3-q1<1e-8,1.0,q3-q1)
        return cls(names,tuple(map(float,med)),tuple(map(float,scale)))
    def transform(self,x: np.ndarray) -> np.ndarray:
        x=np.asarray(x,dtype=np.float32); return ((x-np.asarray(self.median,dtype=np.float32))/np.asarray(self.scale,dtype=np.float32)).astype(np.float32)
    def save(self,path: Path)->None: path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps({"feature_names": self.feature_names, "median": self.median, "scale": self.scale},indent=2),encoding="utf-8")
    @classmethod
    def load(cls,path: Path)->"RobustNormalizer":
        d=json.loads(path.read_text(encoding="utf-8")); return cls(tuple(d["feature_names"]),tuple(d["median"]),tuple(d["scale"]))
