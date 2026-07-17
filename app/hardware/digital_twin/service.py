from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path
from app.hardware.digital_twin.repository import DigitalTwinRepository
from app.hardware.digital_twin.schemas import DigitalTwin, TwinValidationResult
from app.hardware.digital_twin.validator import validate_twin
class DigitalTwinService:
    def __init__(self,repository:DigitalTwinRepository)->None:self.repository=repository
    @classmethod
    def from_project(cls,root:Path)->'DigitalTwinService': return cls(DigitalTwinRepository(root/'data/digital_twins'))
    def create(self,**values)->DigitalTwin:
        now=datetime.now(UTC).isoformat(timespec='milliseconds'); twin=DigitalTwin(schema_version='1.0',created_at_utc=now,updated_at_utc=now,**values); self.repository.save(twin); return twin
    def verify(self,twin_id:str,evidence:dict[str,str])->TwinValidationResult: return validate_twin(self.repository.load(twin_id),evidence)
