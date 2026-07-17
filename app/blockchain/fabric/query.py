"""Read-only Hyperledger Fabric provenance query operations.

Purpose:
    Query committed semiconductor provenance records from Fabric and safely
    decode the canonical record JSON embedded by the chaincode.

Directory:
    app/blockchain/fabric

Dependencies:
    json, typing, FabricClient

Connection:
    BlockchainService uses FabricQuery for provenance reads, chip history,
    integrity verification, and network metadata.
"""

from __future__ import annotations

import json
from typing import Any

from app.blockchain.fabric.client import FabricClient


class FabricQuery:
    """Read-only query facade for semiconductor provenance chaincode."""

    def __init__(self, client: FabricClient) -> None:
        self.client = client

    @staticmethod
    def _normalise_record(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise RuntimeError(
                "Fabric GetProvenance returned an unexpected response type: "
                f"{type(value).__name__}"
            )

        record = dict(value)

        # Fabric/Go JSON normally exposes PascalCase field names unless the
        # model struct defines explicit JSON tags. Support both forms.
        aliases = {
            "DocType": "doc_type",
            "ScanID": "scan_id",
            "ChipID": "chip_id",
            "RecordHash": "record_hash",
            "RecordJSON": "record_json",
            "FabricTransactionID": "fabric_transaction_id",
            "CreatedAtUTC": "created_at_utc",
            "UpdatedAtUTC": "updated_at_utc",
            "EthereumAnchorRoot": "ethereum_anchor_root",
            "EthereumTxHash": "ethereum_tx_hash",
            "Revoked": "revoked",
            "RevocationReasonHash": "revocation_reason_hash",
        }

        for source_key, target_key in aliases.items():
            if source_key in record and target_key not in record:
                record[target_key] = record[source_key]

        embedded = record.get("record_json")

        if isinstance(embedded, str):
            try:
                record["record"] = json.loads(embedded)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Fabric provenance record contains invalid record_json"
                ) from exc
        elif isinstance(embedded, dict):
            record["record"] = embedded
        elif embedded is not None:
            raise RuntimeError(
                "Fabric provenance record_json has an unsupported type: "
                f"{type(embedded).__name__}"
            )

        return record

    def record(self, scan_id: str) -> dict[str, Any]:
        return self.get_provenance(scan_id)

    def chip_history(self, chip_id: str) -> list[dict[str, Any]]:
        return self.get_chip_history(chip_id)

    def verify_hash(self, scan_id: str, record_hash: str) -> bool:
        return self.verify_record_hash(scan_id, record_hash)

    def get_provenance(self, scan_id: str) -> dict[str, Any]:
        response = self.client.evaluate("GetProvenance", [scan_id])
        return self._normalise_record(response)

    def verify_record_hash(self, scan_id: str, record_hash: str) -> bool:
        response = self.client.evaluate(
            "VerifyRecordHash",
            [scan_id, record_hash],
        )

        if isinstance(response, bool):
            return response

        if isinstance(response, str):
            lowered = response.strip().lower()

            if lowered == "true":
                return True

            if lowered == "false":
                return False

        raise RuntimeError(
            "Fabric VerifyRecordHash returned an unexpected response"
        )

    def get_chip_history(self, chip_id: str) -> list[dict[str, Any]]:
        response = self.client.evaluate("GetChipHistory", [chip_id])

        if not isinstance(response, list):
            raise RuntimeError(
                "Fabric GetChipHistory returned an unexpected response type"
            )

        return [
            self._normalise_record(item)
            for item in response
        ]

    def get_network_metadata(self) -> dict[str, Any]:
        response = self.client.evaluate("GetNetworkMetadata")

        if not isinstance(response, dict):
            raise RuntimeError(
                "Fabric GetNetworkMetadata returned an unexpected response"
            )

        return dict(response)
