import numpy as np
from app.ai.feature_extraction import FeatureExtractionService,FEATURE_NAMES
def evidence():
 x=np.linspace(0,10,300)
 return {"side_channel":{"power_trace":np.sin(x).tolist(),"em_trace":np.cos(x).tolist(),"timing_trace":(1+.01*np.sin(x)).tolist()},"yosys":{"gate_count":1000,"cell_count":900},"verilator":{},"supply_chain":{},"puf":{"stability_score":.99},"opentitan":{"verified":True}}
def test_complete_schema():
 f=FeatureExtractionService().extract(evidence()); assert f.names==FEATURE_NAMES; assert len(f.values)==32; assert np.asarray(f.sequence).shape==(256,3)
