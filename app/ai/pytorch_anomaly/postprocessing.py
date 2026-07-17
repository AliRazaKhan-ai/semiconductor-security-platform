"""Map reconstruction error to anomaly probability and confidence."""
from __future__ import annotations
import math
import numpy as np
from app.ai.common import clamp
def postprocess(error:float,per_feature:np.ndarray,threshold:float,scale:float,feature_names:tuple[str,...])->dict:
    z=(error-threshold)/max(scale,1e-9); probability=1/(1+math.exp(-max(-40,min(40,z))))
    distance=abs(error-threshold)/max(scale,1e-9); confidence=clamp(1-math.exp(-distance))
    idx=np.argsort(per_feature)[-5:][::-1]
    return {"label":"ANOMALOUS" if error>=threshold else "NORMAL","score":probability,"confidence":confidence,"reconstruction_error":error,"threshold":threshold,"top_errors":[{"feature":feature_names[i],"error":float(per_feature[i])} for i in idx]}
