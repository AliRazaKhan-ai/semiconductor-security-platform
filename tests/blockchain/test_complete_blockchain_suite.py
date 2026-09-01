"""Purpose: Validate Fabric and Ethereum integration contracts.
Directory: tests/blockchain.
Dependencies: Flask application, blockchain configuration and Go chaincode.
Connection: Protects immutable provenance, SHA-256 verification, private
collections and fail-closed deployment behaviour.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_blockchain_service_is_registered() -> None:
    app = create_app({"TESTING": True})

    service = app.extensions.get("semisecure.blockchain_service")

    assert service is not None


def test_blockchain_status_contract(client) -> None:
    """Validate stable blockchain status fields in all environments."""
    response = client.get("/api/v1/blockchain/status")

    assert response.status_code == 200

    payload = response.get_json()

    assert isinstance(payload, dict)
    assert payload["ok"] is True

    data = payload["data"]

    fabric = data["hyperledger_fabric"]
    ethereum = data["ethereum_anchor"]

    assert isinstance(fabric["enabled"], bool)
    assert isinstance(ethereum["enabled"], bool)

    if "connected" in fabric:
        assert isinstance(fabric["connected"], bool)
    else:
        assert isinstance(fabric.get("connection_state"), str)

    if "connected" in ethereum:
        assert isinstance(ethereum["connected"], bool)
    else:
        assert isinstance(ethereum.get("connection_state"), str)


def test_fabric_chaincode_validates_lowercase_sha256() -> None:
    source = (
        ROOT
        / "blockchain"
        / "fabric"
        / "chaincode"
        / "semiconductor_provenance"
        / "contract.go"
    ).read_text(encoding="utf-8")

    assert r"^[0-9a-f]{64}$" in source
    assert "sha256.Sum256" in source
    assert "record hash does not match canonical record JSON" in source


def test_fabric_chaincode_is_append_only_for_new_scan() -> None:
    source = (
        ROOT
        / "blockchain"
        / "fabric"
        / "chaincode"
        / "semiconductor_provenance"
        / "contract.go"
    ).read_text(encoding="utf-8")

    assert "provenance already exists for scan" in source
    assert "GetState(key)" in source


def test_sensitive_evidence_uses_private_collection() -> None:
    source = (
        ROOT
        / "blockchain"
        / "fabric"
        / "chaincode"
        / "semiconductor_provenance"
        / "contract.go"
    ).read_text(encoding="utf-8")

    assert 'PutPrivateData("collectionSensitiveEvidence"' in source
    assert 'transient["sensitiveRecord"]' in source


def test_chaincode_model_contains_provenance_fields() -> None:
    source = (
        ROOT
        / "blockchain"
        / "fabric"
        / "chaincode"
        / "semiconductor_provenance"
        / "models.go"
    ).read_text(encoding="utf-8")

    required_fields = (
        "ScanID",
        "ChipID",
        "RecordHash",
        "FabricTransactionID",
        "EthereumAnchorRoot",
        "EthereumTxHash",
        "Revoked",
    )

    for field in required_fields:
        assert field in source


def test_ethereum_contract_address_format() -> None:
    config = json.loads(
        (
            ROOT / "configs" / "application" / "blockchain.json"
        ).read_text(encoding="utf-8")
    )

    address = config["blockchain"]["ethereum"]["contract_address"]

    assert re.fullmatch(r"0x[0-9a-fA-F]{40}", address)


def test_blockchain_failure_blocks_required_deployment() -> None:
    source = (
        ROOT / "app" / "pipeline" / "orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "HOLD_PENDING_BLOCKCHAIN_RECOVERY" in source
    assert "INFRASTRUCTURE_HOLD" in source
    assert "stop_pipeline" in source
