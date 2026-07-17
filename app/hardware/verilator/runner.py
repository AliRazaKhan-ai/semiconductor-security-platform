from __future__ import annotations
import tempfile
from pathlib import Path
from app.hardware.common import CommandRunner, HardwareIntegrationError, require_file
from app.hardware.verilator.testbench import validate_testbench
class VerilatorRunner:
    def __init__(self,runner:CommandRunner|None=None)->None:self.runner=runner or CommandRunner(timeout_seconds=240)
    def execute(self,rtl:Path,testbench:Path,top:str)->tuple[str,str]:
        rtl=require_file(rtl,'verilator'); testbench=validate_testbench(testbench)
        with tempfile.TemporaryDirectory(prefix='semisecure-verilator-') as tmp:
            d=Path(tmp); result=self.runner.run(['verilator','--binary','--timing','--assert','-Wall','-Wno-fatal','--top-module',top,str(rtl),str(testbench),'-o','simulation'],cwd=d)
            if not result.succeeded: raise HardwareIntegrationError('verilator','Verilator build failed',{'stderr':result.stderr[-4000:]})
            binary=d/'obj_dir'/'simulation'; run=self.runner.run([str(binary)],cwd=d)
            if not run.succeeded: raise HardwareIntegrationError('verilator','RTL simulation failed',{'stdout':run.stdout[-4000:],'stderr':run.stderr[-4000:]})
            return result.stderr,run.stdout+run.stderr
