"""Ethereum anchoring orchestration. Only a SHA-256 Merkle root leaves Fabric."""
from __future__ import annotations

from app.blockchain.common.schemas import EthereumReceipt
from app.blockchain.ethereum.client import EthereumClient
from app.blockchain.ethereum.merkle import merkle_root
from app.blockchain.ethereum.receipts import ReceiptRepository


class AnchorService:
    def __init__(self, client: EthereumClient, receipts: ReceiptRepository) -> None:
        self.client = client
        self.receipts = receipts

    def anchor_hashes(self, hashes: list[str]) -> EthereumReceipt:
        root = merkle_root(hashes)
        existing = self.receipts.get(root)
        if existing is not None:
            return EthereumReceipt(**existing)
        receipt = self.client.anchor(root)
        self.receipts.put(root, receipt.to_dict())
        return receipt
