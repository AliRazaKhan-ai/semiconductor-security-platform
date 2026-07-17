# Blockchain Integration

## Storage boundary

Hyperledger Fabric is the authoritative consortium ledger. It receives the complete provenance document, pipeline decisions, evidence hashes, model versions, custody information, compliance result, and a private-data transient payload for sensitive evidence. The private payload is written to `collectionSensitiveEvidence`; only its hash is present in the public channel ledger.

Ethereum receives exactly one Solidity argument: a `bytes32` SHA-256 Merkle root. The contract has no function capable of accepting a scan ID, chip ID, supplier, result, metadata, URI, or raw evidence.

## Flow

1. The terminal submits and completes a chip scan through the backend pipeline.
2. The terminal calls `POST /api/v1/blockchain/provenance` with the scan ID.
3. The backend reconstructs the immutable scan history from the JSON event store.
4. A canonical JSON provenance document is SHA-256 hashed.
5. Fabric chaincode validates that the supplied hash matches the record JSON and commits the complete record.
6. The backend records `fabric.committed` and publishes it through Socket.IO.
7. The Fabric record hash becomes a Merkle leaf. A batch can contain one or many Fabric record hashes.
8. Only the resulting 32-byte root is sent to `HashAnchor.anchor(bytes32)` on Ethereum.
9. The confirmed Ethereum transaction receipt is retained locally and the root/transaction reference is attached back to the Fabric record.
10. The backend records `ethereum.anchor_confirmed`; the dashboard updates from Socket.IO and read-only REST queries.

## Failure modes

- Fabric endorsement, ordering, validation, or commit timeout: no Ethereum transaction is attempted.
- Fabric record hash mismatch: chaincode rejects the transaction.
- Duplicate scan record: chaincode rejects non-idempotent overwrite.
- Ethereum chain-ID mismatch, RPC outage, fee estimation failure, revert, or receipt timeout: Fabric remains authoritative and the scan remains unanchored until retry.
- Duplicate Ethereum root: contract rejects it; local receipt lookup provides idempotent recovery.
- Anchor attachment failure after Ethereum confirmation: the receipt remains in the local immutable receipt repository and can be reconciled back into Fabric.

## REST

- `GET /api/v1/blockchain/status`
- `GET /api/v1/blockchain/provenance/<scan_id>`
- `POST /api/v1/blockchain/provenance` — terminal only; body: `{"scan_id":"...","source":"terminal"}`

The dashboard JavaScript uses GET operations only.
