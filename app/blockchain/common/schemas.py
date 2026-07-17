"""Typed blockchain integration contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.blockchain.common.hashing import require_sha256


@dataclass(frozen=True, slots=True)
class FabricSubmission:
    scan_id: str
    chip_id: str
    record_hash: str
    transaction_id: str
    committed: bool
    channel: str
    chaincode: str
    submitted_at_utc: str
    block_number: int | None = None
    validation_code: str = "VALID"

    def __post_init__(self) -> None:
        require_sha256(self.record_hash, field="record_hash")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EthereumReceipt:
    root_hash: str
    transaction_hash: str
    block_number: int
    chain_id: int
    contract_address: str
    confirmations: int
    confirmed: bool
    anchored_at_utc: str

    def __post_init__(self) -> None:
        require_sha256(self.root_hash, field="root_hash")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BlockchainHealth:
    enabled: bool
    connection_state: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
