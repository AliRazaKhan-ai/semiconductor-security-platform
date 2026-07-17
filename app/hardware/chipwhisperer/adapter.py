from __future__ import annotations
from pathlib import Path
from app.hardware.chipwhisperer.analysis import analyse_trace
from app.hardware.chipwhisperer.capture import load_trace
from app.hardware.chipwhisperer.schemas import ChipWhispererResult
from app.hardware.common import load_json
class ChipWhispererAdapter:
    def __init__(self, *, anomaly_threshold:float=0.35)->None: self.threshold=anomaly_threshold
    @classmethod
    def from_project(cls,root:Path)->'ChipWhispererAdapter':
        cfg=load_json(root/'configs/hardware/chipwhisperer.json'); return cls(anomaly_threshold=float(cfg.get('anomaly_threshold',0.35)))
    def analyse_files(self,candidate:Path,reference:Path)->ChipWhispererResult:
        return analyse_trace(load_trace(candidate),load_trace(reference),anomaly_threshold=self.threshold)
