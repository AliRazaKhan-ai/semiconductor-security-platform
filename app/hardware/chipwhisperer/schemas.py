from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
@dataclass(frozen=True, slots=True)
class TraceStatistics:
    samples:int; mean:float; standard_deviation:float; rms:float; peak_to_peak:float; crest_factor:float; spectral_centroid:float; high_frequency_ratio:float; correlation:float
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True, slots=True)
class ChipWhispererResult:
    passed:bool; status:str; anomaly_score:float; threshold:float; reasons:tuple[str,...]; statistics:TraceStatistics; trace_digest:str
    def to_dict(self)->dict[str,Any]: return asdict(self)
