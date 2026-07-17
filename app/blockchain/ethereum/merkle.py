"""Deterministic SHA-256 Merkle tree construction for Ethereum hash anchoring."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.blockchain.common.hashing import require_sha256


def _digest(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(left + right).digest()


@dataclass(frozen=True, slots=True)
class MerkleProofStep:
    sibling: str
    sibling_on_left: bool


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        raise ValueError("at least one hash is required")
    layer = [bytes.fromhex(require_sha256(value)) for value in hashes]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [_digest(layer[index], layer[index + 1]) for index in range(0, len(layer), 2)]
    return layer[0].hex()


def merkle_proof(hashes: list[str], target_index: int) -> list[MerkleProofStep]:
    if target_index < 0 or target_index >= len(hashes):
        raise IndexError("target_index is outside the leaf set")
    layer = [bytes.fromhex(require_sha256(value)) for value in hashes]
    index = target_index
    proof: list[MerkleProofStep] = []
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        sibling_index = index - 1 if index % 2 else index + 1
        proof.append(MerkleProofStep(layer[sibling_index].hex(), sibling_index < index))
        layer = [_digest(layer[position], layer[position + 1]) for position in range(0, len(layer), 2)]
        index //= 2
    return proof


def verify_proof(leaf_hash: str, proof: list[MerkleProofStep], expected_root: str) -> bool:
    current = bytes.fromhex(require_sha256(leaf_hash))
    for step in proof:
        sibling = bytes.fromhex(require_sha256(step.sibling))
        current = _digest(sibling, current) if step.sibling_on_left else _digest(current, sibling)
    return current.hex() == require_sha256(expected_root)
