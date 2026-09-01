from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DigitalTwin:
    schema_version:str; twin_id:str; chip_id:str; manufacturer:str; supplier_id:str; lot_id:str; serial_number:str; puf_identity_hash:str; rtl_digest:str; netlist_digest:str; firmware_digest:str; sbom_digest:str; lifecycle_state:str; custody_hashes:tuple[str,...]; created_at_utc:str; updated_at_utc:str
    def to_dict(self)->dict[str,Any]: return asdict(self)
@dataclass(frozen=True, slots=True)
class TwinValidationResult:
    passed:bool; status:str; reasons:tuple[str,...]; twin_digest:str; mismatches:dict[str,dict[str,str]]
    def to_dict(self)->dict[str,Any]: return asdict(self)
