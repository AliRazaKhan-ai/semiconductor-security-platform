from __future__ import annotations
import json, tempfile
from pathlib import Path
from app.hardware.common import CommandRunner, HardwareIntegrationError, require_file
class YosysRunner:
    def __init__(self,runner:CommandRunner|None=None)->None: self.runner=runner or CommandRunner(timeout_seconds=180)
    def synthesise(self,rtl:Path,top:str)->tuple[dict,str,bytes]:
        rtl=require_file(rtl,'yosys')
        with tempfile.TemporaryDirectory(prefix='semisecure-yosys-') as tmp:
            d=Path(tmp); stat=d/'stat.json'; net=d/'netlist.json'; script=d/'run.ys'
            script.write_text(f'read_verilog -sv {rtl.as_posix()}\nhierarchy -check -top {top}\nproc; opt; check\nwrite_json {net.as_posix()}\nstat -json > {stat.as_posix()}\n',encoding='utf-8')
            result=self.runner.run(['yosys','-q','-s',str(script)],cwd=d)
            if not result.succeeded: raise HardwareIntegrationError('yosys','Yosys synthesis failed',{'stderr':result.stderr[-4000:]})
            try: stats=json.loads(stat.read_text())
            except Exception as exc: raise HardwareIntegrationError('yosys','Yosys did not produce valid statistics') from exc
            return stats,result.stdout+result.stderr,net.read_bytes()
