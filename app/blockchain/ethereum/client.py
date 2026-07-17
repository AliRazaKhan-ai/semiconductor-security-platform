"""Signed Ethereum transaction client that submits only bytes32 hash roots."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.blockchain.common.hashing import bytes32_hex, require_sha256
from app.blockchain.common.schemas import EthereumReceipt
from app.blockchain.ethereum.contract import HASH_ANCHOR_ABI


class EthereumClient:
    def __init__(
        self,
        *,
        rpc_url: str,
        chain_id: int,
        contract_address: str,
        private_key: str,
        confirmations: int = 1,
        receipt_timeout_seconds: int = 180,
        web3_instance: Any | None = None,
    ) -> None:
        try:
            from web3 import Web3
        except ImportError as exc:
            raise RuntimeError("web3 is required for Ethereum anchoring") from exc
        self.Web3 = Web3
        self.web3 = web3_instance or Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        self.chain_id = int(chain_id)
        self.private_key = private_key
        self.confirmations = max(1, int(confirmations))
        self.receipt_timeout_seconds = int(receipt_timeout_seconds)
        self.account = self.web3.eth.account.from_key(private_key)
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract = self.web3.eth.contract(address=self.contract_address, abi=HASH_ANCHOR_ABI)

    def health(self) -> dict[str, Any]:
        connected = bool(self.web3.is_connected())
        remote_chain = int(self.web3.eth.chain_id) if connected else None
        return {
            "connected": connected,
            "chain_id": remote_chain,
            "configured_chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "account_address": self.account.address,
        }

    def is_anchored(self, root_hash: str) -> bool:
        root = bytes.fromhex(require_sha256(root_hash, field="root_hash"))
        return bool(self.contract.functions.isAnchored(root).call())

    def anchor(self, root_hash: str) -> EthereumReceipt:
        normalized = require_sha256(root_hash, field="root_hash")
        root_bytes = bytes.fromhex(normalized)
        if self.is_anchored(normalized):
            raise ValueError("hash root is already anchored")
        if int(self.web3.eth.chain_id) != self.chain_id:
            raise RuntimeError("Ethereum chain ID does not match configuration")
        nonce = self.web3.eth.get_transaction_count(self.account.address, "pending")
        function = self.contract.functions.anchor(root_bytes)
        estimated_gas = int(function.estimate_gas({"from": self.account.address}))
        base_fee = int(self.web3.eth.get_block("pending").get("baseFeePerGas", self.web3.eth.gas_price))
        priority_fee = int(getattr(self.web3.eth, "max_priority_fee", self.web3.to_wei(1, "gwei")))
        transaction = function.build_transaction({
            "from": self.account.address,
            "chainId": self.chain_id,
            "nonce": nonce,
            "gas": max(estimated_gas * 120 // 100, 50_000),
            "maxFeePerGas": base_fee * 2 + priority_fee,
            "maxPriorityFeePerGas": priority_fee,
            "value": 0,
        })
        signed = self.account.sign_transaction(transaction)
        transaction_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(
            transaction_hash,
            timeout=self.receipt_timeout_seconds,
            poll_latency=1,
        )
        if int(receipt.status) != 1:
            raise RuntimeError("Ethereum anchoring transaction reverted")
        target_block = int(receipt.blockNumber) + self.confirmations - 1
        while int(self.web3.eth.block_number) < target_block:
            self.web3.eth.wait_for_block(target_block, timeout=self.receipt_timeout_seconds)
        return EthereumReceipt(
            root_hash=normalized,
            transaction_hash=transaction_hash.hex(),
            block_number=int(receipt.blockNumber),
            chain_id=self.chain_id,
            contract_address=self.contract_address,
            confirmations=self.confirmations,
            confirmed=True,
            anchored_at_utc=datetime.now(UTC).isoformat(),
        )
