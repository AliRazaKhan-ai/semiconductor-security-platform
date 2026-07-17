"""Run known-Trojan TensorFlow CNN inference."""
from __future__ import annotations
from typing import Any,Protocol
from app.constants import EventType
from app.storage.event_store import EventStore
from app.storage.event_store.schemas import EventRecord
class Publisher(Protocol):
 def publish_record(self,record:EventRecord)->None: ...
class TensorFlowStage:
 name="TENSORFLOW_CLASSIFICATION"; component="tensorflow-stage"
 def __init__(self,service,event_store:EventStore,publisher:Publisher|None=None,component_version:str="1.0.0"): self.service=service; self.event_store=event_store; self.publisher=publisher; self.component_version=component_version
 def execute(self,*,scan_id:str,chip_id:str,correlation_id:str,sequence):
  self._persist(scan_id,chip_id,correlation_id,EventType.STAGE_STARTED,{"status":"PROCESSING"})
  try:
   result=self.service.infer(sequence).to_dict()
   self._persist(scan_id,chip_id,correlation_id,EventType.STAGE_COMPLETED,{"status":"PASSED","result":result})
   return {"passed":True,"result":result}
  except Exception as exc:
   failure={"status":"FAILED","stop_pipeline":True,"error_type":type(exc).__name__,"message":str(exc)}
   self._persist(scan_id,chip_id,correlation_id,EventType.STAGE_FAILED,failure); return {"passed":False,"failure":failure}
 def _persist(self,scan_id,chip_id,correlation_id,event_type,payload):
  record=self.event_store.append(scan_id=scan_id,chip_id=chip_id,event_type=str(event_type),pipeline_stage=self.name,correlation_id=correlation_id,source_component=self.component,component_version=self.component_version,payload=payload)
  if self.publisher:self.publisher.publish_record(record)
