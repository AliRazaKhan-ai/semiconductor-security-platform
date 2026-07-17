from __future__ import annotations
import hashlib, uuid
from datetime import UTC, datetime
from pathlib import Path
from app.hardware.common import atomic_write_json, canonical_json, sha256_file
from app.hardware.sbom.schemas import SBOMComponent, SBOMResult
class SBOMGenerator:
    def generate(self,*,chip_id:str,artifacts:list[Path],output:Path,metadata:dict[str,str]|None=None)->SBOMResult:
        components=[]
        for artifact in sorted((p.resolve(strict=True) for p in artifacts),key=lambda p:p.name):
            components.append(SBOMComponent('file',artifact.name,str((metadata or {}).get(f'version:{artifact.name}','unknown')),str((metadata or {}).get(f'supplier:{artifact.name}','unknown')),{'SHA-256':sha256_file(artifact)},tuple(),{'absolute_path':str(artifact)}))
        serial=f'urn:uuid:{uuid.uuid4()}'
        document={'bomFormat':'CycloneDX','specVersion':'1.5','serialNumber':serial,'version':1,'metadata':{'timestamp':datetime.now(UTC).isoformat(timespec='seconds'),'component':{'type':'device','name':chip_id}},'components':[c.to_dict() for c in components]}
        digest=hashlib.sha256(canonical_json(document)).hexdigest(); document['properties']=[{'name':'semisecure:document-sha256','value':digest}]
        atomic_write_json(output,document)
        reasons=tuple(['EMPTY_SBOM'] if not components else [])
        return SBOMResult(not reasons,'GENERATED' if not reasons else 'REJECTED',reasons,serial,len(components),digest,str(output))
