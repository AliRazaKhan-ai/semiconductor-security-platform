"""Commit confirmation abstraction.

The peer CLI submit path uses --waitForEvent, so a returned transaction ID is already
endorsed, ordered, validated, and observed as committed by the configured peer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommitStatus:
    transaction_id: str
    committed: bool = True
    validation_code: str = "VALID"


class CommitMonitor:
    def confirmed(self, transaction_id: str) -> CommitStatus:
        if not transaction_id:
            raise ValueError("transaction_id is required")
        return CommitStatus(transaction_id=transaction_id)
