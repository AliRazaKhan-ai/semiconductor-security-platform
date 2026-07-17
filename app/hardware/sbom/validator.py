from __future__ import annotations
from pathlib import Path
from app.hardware.common import load_json, sha256_file
def validate_sbom(path:Path,forbidden_licenses:set[str]|None=None)->tuple[str,...]:
    d=load_json(path); reasons=[]
    if d.get('bomFormat')!='CycloneDX': reasons.append('UNSUPPORTED_SBOM_FORMAT')
    if not isinstance(d.get('components'),list) or not d['components']: reasons.append('SBOM_COMPONENTS_MISSING')
    forbidden=forbidden_licenses or set()
    for c in d.get('components',[]):
        for lic in c.get('licenses',[]):
            value=lic.get('license',{}).get('id') if isinstance(lic,dict) else str(lic)
            if value in forbidden: reasons.append('FORBIDDEN_LICENSE')
    return tuple(sorted(set(reasons)))
