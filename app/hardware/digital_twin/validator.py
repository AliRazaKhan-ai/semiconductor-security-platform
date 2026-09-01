from __future__ import annotations

import hashlib

from app.hardware.common import canonical_json
from app.hardware.digital_twin.schemas import DigitalTwin, TwinValidationResult


def validate_twin(twin:DigitalTwin,evidence:dict[str,str])->TwinValidationResult:
    fields=('chip_id','puf_identity_hash','rtl_digest','netlist_digest','firmware_digest','sbom_digest')
    mismatches={}
    for field in fields:
        expected=str(getattr(twin,field)); actual=str(evidence.get(field,''))
        if expected!=actual: mismatches[field]={'expected':expected,'actual':actual}
    reasons=tuple(f'{field.upper()}_MISMATCH' for field in mismatches)
    digest=hashlib.sha256(canonical_json(twin.to_dict())).hexdigest()
    return TwinValidationResult(not reasons,'VERIFIED' if not reasons else 'MISMATCH',reasons,digest,mismatches)
