from __future__ import annotations
from pathlib import Path
from typing import Any
from app.hardware.common import HardwareIntegrationError, load_json, require_file

def load_trace(path:Path)->list[float]:
    data=load_json(require_file(path,'chipwhisperer'))
    values=data.get('samples')
    if not isinstance(values,list): raise HardwareIntegrationError('chipwhisperer','trace JSON requires a samples array')
    try: return [float(v) for v in values]
    except (TypeError,ValueError) as exc: raise HardwareIntegrationError('chipwhisperer','trace contains a non-numeric sample') from exc
