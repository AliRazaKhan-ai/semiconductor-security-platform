from __future__ import annotations
from pathlib import Path
from app.hardware.common import require_file
def validate_testbench(path:Path)->Path:
    path=require_file(path,'verilator'); text=path.read_text(encoding='utf-8',errors='replace')
    if '$finish' not in text and '$fatal' not in text: raise ValueError('testbench must contain an explicit $finish or $fatal')
    return path
