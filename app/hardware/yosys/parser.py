from __future__ import annotations
from app.hardware.yosys.schemas import YosysMetrics
def parse_metrics(stats:dict,top:str)->YosysMetrics:
    modules=stats.get('modules',{}); module=modules.get(top) or modules.get('\\'+top)
    if not isinstance(module,dict): raise ValueError(f'top module not found in Yosys statistics: {top}')
    return YosysMetrics(int(module.get('num_wires',0)),int(module.get('num_wire_bits',0)),int(module.get('num_pub_wires',0)),int(module.get('num_cells',0)),int(module.get('num_processes',0)),int(module.get('num_memories',0)),int(module.get('num_memory_bits',0)),{str(k):int(v) for k,v in module.get('num_cells_by_type',{}).items()})
