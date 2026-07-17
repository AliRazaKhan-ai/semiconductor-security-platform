from __future__ import annotations
import base64, json, os
from pathlib import Path
from app.hardware.common import HardwareIntegrationError, load_json, require_file
from app.hardware.opentitan.attestation import OpenTitanAttestationVerifier
from app.hardware.opentitan.schemas import OpenTitanEvidence, OpenTitanResult

class OpenTitanAdapter:
    def __init__(self, verifier: OpenTitanAttestationVerifier) -> None: self.verifier=verifier
    @classmethod
    def from_project(cls, project_root: Path) -> 'OpenTitanAdapter':
        cfg=load_json(project_root/'configs/hardware/opentitan.json')
        raw=os.getenv('SEMISURE_OPENTITAN_VERIFICATION_KEY','')
        if not raw: raise HardwareIntegrationError('opentitan','SEMISURE_OPENTITAN_VERIFICATION_KEY is required')
        key=base64.b64decode(raw[7:]) if raw.startswith('base64:') else bytes.fromhex(raw[4:]) if raw.startswith('hex:') else raw.encode()
        return cls(OpenTitanAttestationVerifier(trusted_firmware_digests=set(cfg['trusted_firmware_digests']),verification_key=key,allowed_lifecycle_states=set(cfg['allowed_lifecycle_states']),minimum_counter=int(cfg.get('minimum_counter',0))))
    def verify_file(self,path: Path)->OpenTitanResult:
        data=load_json(require_file(path,'opentitan'))
        evidence=OpenTitanEvidence(device_id=str(data['device_id']),lifecycle_state=str(data['lifecycle_state']),boot_stage=str(data['boot_stage']),rom_digest=str(data['rom_digest']),firmware_digest=str(data['firmware_digest']),otp_digest=str(data['otp_digest']),monotonic_counter=int(data['monotonic_counter']),nonce=str(data['nonce']),signature=str(data['signature']),certificate_chain=tuple(map(str,data.get('certificate_chain',[]))),timestamp_utc=str(data['timestamp_utc']))
        return self.verifier.verify(evidence)
