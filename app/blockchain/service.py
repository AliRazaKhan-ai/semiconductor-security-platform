"""Application service coordinating Fabric provenance and Ethereum hash anchoring."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.blockchain.ethereum.anchor_service import AnchorService
from app.blockchain.ethereum.client import EthereumClient
from app.blockchain.ethereum.receipts import ReceiptRepository
from app.blockchain.fabric.client import FabricClient
from app.blockchain.fabric.identity import FabricIdentity
from app.blockchain.fabric.query import FabricQuery
from app.blockchain.fabric.transactions import FabricTransactions


class BlockchainService:
    def __init__(self, *, root: Path, config: dict[str, Any], event_store: Any, publisher: Any | None) -> None:
        self.root = root
        self.config = config
        self.event_store = event_store
        self.publisher = publisher
        self.fabric_enabled = bool(config.get("fabric", {}).get("enabled", False))
        self.ethereum_enabled = bool(config.get("ethereum", {}).get("enabled", False))
        self.fabric_client: FabricClient | None = None
        self.fabric_transactions: FabricTransactions | None = None
        self.fabric_query: FabricQuery | None = None
        self.anchor_service: AnchorService | None = None
        self.ethereum_client: EthereumClient | None = None
        if self.fabric_enabled:
            fabric = dict(config["fabric"])
            identity = FabricIdentity.from_config(root, dict(fabric["identity"]))
            self.fabric_client = FabricClient(
                identity=identity,
                channel=str(fabric["channel"]),
                chaincode=str(fabric["chaincode"]),
                timeout_seconds=int(fabric.get("timeout_seconds", 120)),
                wait_for_event_timeout=str(fabric.get("wait_for_event_timeout", "60s")),
            )
            self.fabric_transactions = FabricTransactions(self.fabric_client)
            self.fabric_query = FabricQuery(self.fabric_client)
        if self.ethereum_enabled:
            ethereum = dict(config["ethereum"])
            private_key = str(ethereum.get("private_key", ""))
            if private_key.startswith("env:"):
                import os
                variable = private_key.split(":", 1)[1]
                private_key = os.environ.get(variable, "")
            if not private_key:
                raise RuntimeError("Ethereum private key is not configured")
            self.ethereum_client = EthereumClient(
                rpc_url=str(ethereum["rpc_url"]),
                chain_id=int(ethereum["chain_id"]),
                contract_address=str(ethereum["contract_address"]),
                private_key=private_key,
                confirmations=int(ethereum.get("confirmations", 1)),
                receipt_timeout_seconds=int(ethereum.get("receipt_timeout_seconds", 180)),
            )
            receipt_root = Path(str(ethereum.get("receipt_root", "data/blockchain/ethereum_receipts")))
            if not receipt_root.is_absolute():
                receipt_root = root / receipt_root
            self.anchor_service = AnchorService(self.ethereum_client, ReceiptRepository(receipt_root))

    def _publish(self, event: Any) -> None:
        if self.publisher is not None:
            self.publisher.publish_record(event)

    def record_scan(self, scan_id: str, correlation_id: str) -> dict[str, Any]:
        if not self.fabric_transactions:
            raise RuntimeError("Hyperledger Fabric integration is disabled")
        snapshot = self.event_store.snapshot(scan_id)
        chip_id = str(snapshot["chip_id"])
        events = [event.to_dict() for event in self.event_store.events(scan_id, limit=10_000)]
        record = {
            "schema_version": "1.0",
            "scan_id": scan_id,
            "chip_id": chip_id,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "current_status": snapshot.get("status"),
            "final_decision": snapshot.get("final_decision"),
            "risk": snapshot.get("risk"),
            "compliance": snapshot.get("compliance"),
            "hardware": snapshot.get("hardware"),
            "ai": snapshot.get("ai"),
            "event_chain_head": snapshot.get("last_event_hash"),
            "event_count": len(events),
            "events": events,
        }
        latest_payload = snapshot.get("latest_payload", {})
        metadata = latest_payload.get("metadata", {})

        sensitive_candidates = {
            "evidence": latest_payload.get("evidence"),
            "supplier": metadata.get("supplier"),
            "digital_twin": latest_payload.get("digital_twin"),
        }
        sensitive = {
            key: value
            for key, value in sensitive_candidates.items()
            if value is not None
        }
        submission = self.fabric_transactions.record_provenance(
            record,
            sensitive=sensitive or None,
        )
        fabric_event = self.event_store.append(
            scan_id=scan_id,
            chip_id=chip_id,
            event_type="fabric.committed",
            pipeline_stage="HYPERLEDGER_FABRIC",
            correlation_id=correlation_id,
            source_component="fabric-adapter",
            component_version="1.0.0",
            payload=submission.to_dict(),
        )
        self._publish(fabric_event)
        result: dict[str, Any] = {"fabric": submission.to_dict(), "ethereum": None}
        if self.anchor_service and self.fabric_transactions:
            receipt = self.anchor_service.anchor_hashes([submission.record_hash])
            self.fabric_transactions.update_anchor(scan_id, receipt.root_hash, receipt.transaction_hash)
            ethereum_event = self.event_store.append(
                scan_id=scan_id,
                chip_id=chip_id,
                event_type="ethereum.anchor_confirmed",
                pipeline_stage="ETHEREUM_HASH_ANCHOR",
                correlation_id=correlation_id,
                source_component="ethereum-anchor",
                component_version="1.0.0",
                payload=receipt.to_dict(),
            )
            self._publish(ethereum_event)
            result["ethereum"] = receipt.to_dict()
        return result

    def provenance(self, scan_id: str) -> dict[str, Any]:
        if not self.fabric_query:
            raise RuntimeError("Hyperledger Fabric integration is disabled")
        record = self.fabric_query.record(scan_id)
        root_hash = record.get("ethereum_anchor_root")
        receipt = None
        if root_hash and self.anchor_service:
            receipt = self.anchor_service.receipts.get(root_hash)
        return {"fabric": record, "ethereum": receipt}

    def status(self) -> dict[str, Any]:
        fabric_state: dict[str, Any] = {"enabled": self.fabric_enabled, "connection_state": "disabled"}
        ethereum_state: dict[str, Any] = {"enabled": self.ethereum_enabled, "connection_state": "disabled"}
        if self.fabric_enabled and self.fabric_client:
            try:
                details = self.fabric_client.health()
                fabric_state = {"enabled": True, "connection_state": "connected", **details}
            except Exception as exc:
                fabric_state = {"enabled": True, "connection_state": "error", "error": str(exc)}
        if self.ethereum_enabled and self.ethereum_client:
            try:
                details = self.ethereum_client.health()
                state = "connected" if details.get("connected") else "disconnected"
                ethereum_state = {"enabled": True, "connection_state": state, **details}
            except Exception as exc:
                ethereum_state = {"enabled": True, "connection_state": "error", "error": str(exc)}
        return {
            "hyperledger_fabric": fabric_state,
            "ethereum_anchor": ethereum_state,
            "storage_policy": {
                "fabric": "complete provenance, evidence hashes, decisions, and private collections",
                "ethereum": "bytes32 SHA-256 Merkle roots only",
            },
        }
