from __future__ import annotations

import hashlib
from pathlib import Path

from app.hardware.common import sha256_file
from app.hardware.verilator.result_parser import parse_output
from app.hardware.verilator.runner import VerilatorRunner
from app.hardware.verilator.schemas import VerilatorResult


class VerilatorAdapter:
    def __init__(self,runner:VerilatorRunner|None=None)->None:self.runner=runner or VerilatorRunner()
    def simulate(self,rtl:Path,testbench:Path,top:str)->VerilatorResult:
        build,output=self.runner.execute(rtl,testbench,top); reasons,assertions,cycles,warnings=parse_output(build,output)
        return VerilatorResult(not reasons,'PASS' if not reasons else 'FAIL',reasons,assertions,cycles,warnings,hashlib.sha256(output.encode()).hexdigest(),sha256_file(rtl),sha256_file(testbench))
