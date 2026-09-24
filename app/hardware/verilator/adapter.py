from __future__ import annotations

import hashlib
from pathlib import Path

from app.hardware.common import sha256_file
from app.hardware.verilator.result_parser import parse_output
from app.hardware.verilator.runner import VerilatorRunner
from app.hardware.verilator.schemas import VerilatorResult


class VerilatorAdapter:
    def __init__(self,runner:VerilatorRunner|None=None)->None:
        self.runner=runner or VerilatorRunner()
        # Verilator translates the RTL and testbench to C++ and builds them with
        # gcc. Measured on a full scan: 24.26s of a 25.36s hardware stage, 98.6%.
        # Seven of the eight fixtures submit byte-identical RTL, so the same model
        # was rebuilt seven times.
        #
        # Keyed on the RTL digest, the testbench digest and the top module, so a
        # changed input is a different key and cannot hit a stale entry. The cached
        # value is the raw (build, output) pair execute() returns, and every field
        # of VerilatorResult derives from it, so a hit is byte-identical to a run.
        #
        # In memory on the adapter. HardwareSecurityPipeline is constructed once in
        # app/factory.py, so the cache persists across scans in a process, which is
        # where the eight-chip run spends its time.
        self._cache:dict[tuple[str,str,str],tuple[str,str]]={}
    def simulate(self,rtl:Path,testbench:Path,top:str)->VerilatorResult:
        rtl_digest=sha256_file(rtl); testbench_digest=sha256_file(testbench)
        key=(rtl_digest,testbench_digest,str(top))
        cached=self._cache.get(key)
        if cached is None:
            cached=self.runner.execute(rtl,testbench,top); self._cache[key]=cached
        build,output=cached; reasons,assertions,cycles,warnings=parse_output(build,output)
        return VerilatorResult(not reasons,'PASS' if not reasons else 'FAIL',reasons,assertions,cycles,warnings,hashlib.sha256(output.encode()).hexdigest(),rtl_digest,testbench_digest)
