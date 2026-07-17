"""Load validated NPZ training datasets shared by all model trainers."""
from __future__ import annotations
from pathlib import Path
import numpy as np
def load_dataset(path:Path):
 d=np.load(path,allow_pickle=False)
 required={"features","sequences","labels"}
 if not required.issubset(d.files): raise ValueError(f"dataset must contain {sorted(required)}")
 x=np.asarray(d["features"],dtype=np.float32); s=np.asarray(d["sequences"],dtype=np.float32); y=np.asarray(d["labels"],dtype=np.int64)
 if x.ndim!=2 or s.ndim!=3 or s.shape[-1]!=3 or len(x)!=len(s) or len(x)!=len(y): raise ValueError("invalid dataset dimensions")
 return x,s,y
