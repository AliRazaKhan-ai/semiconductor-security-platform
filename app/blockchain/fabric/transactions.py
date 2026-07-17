"""High-level Fabric provenance transaction operations."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.blockchain.common.hashing import provenance_digest, require_sha256
from app.blockchain.common.schemas import FabricSubmission
from app.blockchain.fabric.client import FabricClient
from app.blockchain.fabric.private_data import transient_json


class FabricTransactions:
    def __init__(self, client: FabricClient) -> None:
        self.client = client

    def record_provenance(
        self,
        record: dict[str, Any],
        *,
        sensitive: dict[str, Any] | None = None,
    ) -> FabricSubmission:
        scan_id = str(record["scan_id"])
        chip_id = str(record["chip_id"])
        record_hash = provenance_digest(record)
        arguments = [scan_id, chip_id, record_hash, json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)]
        transient = transient_json("sensitiveRecord", sensitive) if sensitive else None
        tx_id = self.client.submit("RecordProvenance", arguments, transient=transient)
        return FabricSubmission(
            scan_id=scan_id,
            chip_id=chip_id,
            record_hash=record_hash,
            transaction_id=tx_id,
            committed=True,
            channel=self.client.channel,
            chaincode=self.client.chaincode,
            submitted_at_utc=datetime.now(UTC).isoformat(),
        )

    def update_anchor(self, scan_id: str, root_hash: str, ethereum_tx_hash: str) -> str:
        require_sha256(root_hash, field="root_hash")
        return self.client.submit("AttachEthereumAnchor", [scan_id, root_hash, ethereum_tx_hash])

    def revoke(self, scan_id: str, reason_hash: str) -> str:
        require_sha256(reason_hash, field="reason_hash")
        return self.client.submit("RevokeProvenance", [scan_id, reason_hash])
