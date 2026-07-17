import numpy as np
from app.ai.pytorch_anomaly.postprocessing import postprocess
def test_anomaly_threshold():
 r=postprocess(.2,np.arange(32),.1,.02,tuple(map(str,range(32)))); assert r['label']=='ANOMALOUS'; assert r['score']>.9; assert len(r['top_errors'])==5
