from __future__ import annotations
import hashlib, hmac, re
from datetime import UTC, datetime
from typing import Any
from app.hardware.common import canonical_json, HardwareIntegrationError
from app.hardware.opentitan.schemas import OpenTitanEvidence, OpenTitanResult

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
class OpenTitanAttestationVerifier:
    def __init__(self, *, trusted_firmware_digests: set[str], verification_key: bytes, allowed_lifecycle_states: set[str], minimum_counter: int = 0) -> None:
        if len(verification_key) < 32: raise ValueError("verification_key must be at least 32 bytes")
        self.trusted_firmware_digests={x.lower() for x in trusted_firmware_digests}; self.key=verification_key
        self.allowed_states={x.upper() for x in allowed_lifecycle_states}; self.minimum_counter=minimum_counter
    def _signed(self,e: OpenTitanEvidence)->bytes:
        d=e.to_dict(); d.pop('signature'); return canonical_json(d)
    def verify(self,e: OpenTitanEvidence)->OpenTitanResult:
        reasons=[]
        if e.lifecycle_state.upper() not in self.allowed_states: reasons.append('LIFECYCLE_STATE_NOT_ALLOWED')
        for name,val in [('rom_digest',e.rom_digest),('firmware_digest',e.firmware_digest),('otp_digest',e.otp_digest)]:
            if not _HEX64.fullmatch(val.lower()): reasons.append(f'INVALID_{name.upper()}')
        if e.firmware_digest.lower() not in self.trusted_firmware_digests: reasons.append('UNTRUSTED_FIRMWARE')
        if e.monotonic_counter < self.minimum_counter: reasons.append('ROLLBACK_COUNTER')
        expected=hmac.new(self.key,self._signed(e),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,e.signature.lower()): reasons.append('INVALID_ATTESTATION_SIGNATURE')
        try:
            ts=datetime.fromisoformat(e.timestamp_utc.replace('Z','+00:00'))
            if ts.tzinfo is None: reasons.append('TIMESTAMP_NOT_UTC')
        except ValueError: reasons.append('INVALID_TIMESTAMP')
        digest=hashlib.sha256(canonical_json(e.to_dict())).hexdigest()
        return OpenTitanResult(not reasons,'ATTESTED' if not reasons else 'REJECTED',tuple(reasons),digest,e.lifecycle_state,e.firmware_digest,e.monotonic_counter)
