from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

from app.hardware.chipwhisperer.analysis import analyse_trace
from app.hardware.common import canonical_json
from app.hardware.digital_twin.schemas import DigitalTwin
from app.hardware.digital_twin.validator import validate_twin
from app.hardware.opentitan.attestation import OpenTitanAttestationVerifier
from app.hardware.opentitan.schemas import OpenTitanEvidence
from app.hardware.sbom.generator import SBOMGenerator


def test_opentitan_attestation():
    key=b'k'*32; fw='1'*64
    e=OpenTitanEvidence('d','PROD','ROM_EXT','2'*64,fw,'3'*64,7,'ab'*16,'',(),datetime.now(UTC).isoformat())
    d=e.to_dict();d.pop('signature');sig=hmac.new(key,canonical_json(d),hashlib.sha256).hexdigest();e=OpenTitanEvidence(**{**e.to_dict(),'signature':sig})
    assert OpenTitanAttestationVerifier(trusted_firmware_digests={fw},verification_key=key,allowed_lifecycle_states={'PROD'}).verify(e).passed

def test_chipwhisperer_clean_and_bad():
    ref=[float((i%17)-8) for i in range(256)]
    assert analyse_trace(ref,ref).passed
    bad=[float((i*31)%97) for i in range(256)]
    assert not analyse_trace(bad,ref,anomaly_threshold=.1).passed

def test_digital_twin_match():
    values=dict(schema_version='1.0',twin_id='t',chip_id='c',manufacturer='m',supplier_id='s',lot_id='l',serial_number='n',puf_identity_hash='p',rtl_digest='r',netlist_digest='n1',firmware_digest='f',sbom_digest='b',lifecycle_state='PROD',custody_hashes=(),created_at_utc='x',updated_at_utc='x')
    twin=DigitalTwin(**values); evidence={k:values[k] for k in ('chip_id','puf_identity_hash','rtl_digest','netlist_digest','firmware_digest','sbom_digest')}
    assert validate_twin(twin,evidence).passed

def test_sbom(tmp_path:Path):
    artifact=tmp_path/'fw.bin';artifact.write_bytes(b'firmware');out=tmp_path/'bom.json'
    result=SBOMGenerator().generate(chip_id='c',artifacts=[artifact],output=out)
    assert result.passed and out.exists()
