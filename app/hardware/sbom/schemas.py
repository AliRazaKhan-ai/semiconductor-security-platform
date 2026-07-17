from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
@dataclass(frozen=True, slots=True)
class SBOMComponent:
    component_type:str; name:str; version:str; supplier:str; hashes:dict[str,str]; licenses:tuple[str,...]; properties:dict[str,str]
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True, slots=True)
class SBOMResult:
    passed:bool; status:str; reasons:tuple[str,...]; serial_number:str; component_count:int; document_digest:str; path:str
    def to_dict(self)->dict[str,Any]: return asdict(self)
