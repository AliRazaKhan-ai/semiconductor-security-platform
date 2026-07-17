from __future__ import annotations
import re
from pathlib import Path
from app.hardware.common import atomic_write_json, load_json
from app.hardware.digital_twin.schemas import DigitalTwin
_SAFE=re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
class DigitalTwinRepository:
    def __init__(self,root:Path)->None:self.root=root; root.mkdir(parents=True,exist_ok=True)
    def path(self,twin_id:str)->Path:
        if not _SAFE.fullmatch(twin_id): raise ValueError('invalid twin identifier')
        return self.root/f'{twin_id}.json'
    def save(self,twin:DigitalTwin,replace:bool=False)->None:
        p=self.path(twin.twin_id)
        if p.exists() and not replace: raise FileExistsError(p)
        atomic_write_json(p,twin.to_dict())
    def load(self,twin_id:str)->DigitalTwin:
        d=load_json(self.path(twin_id)); d['custody_hashes']=tuple(d.get('custody_hashes',[])); return DigitalTwin(**d)
