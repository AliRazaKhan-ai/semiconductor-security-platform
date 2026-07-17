from __future__ import annotations
from app.hardware.yosys.schemas import YosysMetrics
def evaluate(metrics:YosysMetrics, policy:dict)->tuple[str,...]:
    reasons=[]
    limits={'cells':metrics.cells,'wire_bits':metrics.wire_bits,'memory_bits':metrics.memory_bits}
    for name,value in limits.items():
        maximum=int(policy.get(f'maximum_{name}',10**9))
        if value>maximum: reasons.append(f'{name.upper()}_LIMIT_EXCEEDED')
    forbidden={str(x) for x in policy.get('forbidden_cell_types',[])}
    if forbidden.intersection(metrics.cell_types): reasons.append('FORBIDDEN_CELL_TYPE')
    required={str(x) for x in policy.get('required_cell_types',[])}
    if not required.issubset(metrics.cell_types): reasons.append('REQUIRED_CELL_TYPE_MISSING')
    return tuple(reasons)
