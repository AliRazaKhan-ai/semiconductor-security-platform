from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
@dataclass(frozen=True, slots=True)
class VerilatorResult:
    passed:bool; status:str; reasons:tuple[str,...]; assertions:int; cycles:int; warnings:tuple[str,...]; stdout_digest:str; rtl_digest:str; testbench_digest:str
    def to_dict(self)->dict[str,Any]: return asdict(self)
