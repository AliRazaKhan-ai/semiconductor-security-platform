from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class YosysMetrics:
    wires:int; wire_bits:int; public_wires:int; cells:int; processes:int; memories:int; memory_bits:int; cell_types:dict[str,int]
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True, slots=True)
class YosysResult:
    passed:bool; status:str; reasons:tuple[str,...]; metrics:YosysMetrics; rtl_digest:str; netlist_digest:str; log_digest:str
    def to_dict(self)->dict[str,Any]: return asdict(self)
