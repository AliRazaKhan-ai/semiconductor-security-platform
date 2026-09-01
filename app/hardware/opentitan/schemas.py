from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OpenTitanEvidence:
    device_id: str
    lifecycle_state: str
    boot_stage: str
    rom_digest: str
    firmware_digest: str
    otp_digest: str
    monotonic_counter: int
    nonce: str
    signature: str
    certificate_chain: tuple[str, ...]
    timestamp_utc: str
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True, slots=True)
class OpenTitanResult:
    passed: bool
    status: str
    reasons: tuple[str, ...]
    evidence_digest: str
    lifecycle_state: str
    firmware_digest: str
    monotonic_counter: int
    def to_dict(self) -> dict[str, Any]: return asdict(self)
