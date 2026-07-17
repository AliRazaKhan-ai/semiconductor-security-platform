"""Extract human-readable feature importance from supported sklearn estimators."""
from __future__ import annotations
import numpy as np
def explain(model,feature_names,values,limit:int=8):
 imp=getattr(model,"feature_importances_",None)
 if imp is None: return []
 imp=np.asarray(imp,dtype=float); vals=np.asarray(values,dtype=float); idx=np.argsort(np.abs(imp*vals))[-limit:][::-1]
 return [{"feature":feature_names[i],"importance":float(imp[i]),"value":float(vals[i]),"contribution":float(imp[i]*vals[i])} for i in idx]
