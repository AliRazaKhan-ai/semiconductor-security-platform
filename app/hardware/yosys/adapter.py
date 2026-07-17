from __future__ import annotations
import hashlib
from pathlib import Path
from app.hardware.common import load_json, sha256_file
from app.hardware.yosys.parser import parse_metrics
from app.hardware.yosys.rules import evaluate
from app.hardware.yosys.runner import YosysRunner
from app.hardware.yosys.schemas import YosysResult
class YosysAdapter:
    def __init__(self,policy:dict,runner:YosysRunner|None=None)->None: self.policy=policy; self.runner=runner or YosysRunner()
    @classmethod
    def from_project(cls,root:Path)->'YosysAdapter': return cls(load_json(root/'configs/hardware/yosys.json'))
    def analyse(self,rtl:Path,top:str)->YosysResult:
        stats,log,netlist=self.runner.synthesise(rtl,top); metrics=parse_metrics(stats,top); reasons=evaluate(metrics,self.policy)
        return YosysResult(not reasons,'PASS' if not reasons else 'FAIL',reasons,metrics,sha256_file(rtl),hashlib.sha256(netlist).hexdigest(),hashlib.sha256(log.encode()).hexdigest())
