from __future__ import annotations
from statistics import mean

def aggregate_reference(traces:list[list[float]])->list[float]:
    if not traces: raise ValueError('at least one trace is required')
    length=min(map(len,traces)); return [mean(trace[i] for trace in traces) for i in range(length)]
