"""Purpose: Validate deterministic core integration utilities.
Directory: tests/unit.
Dependencies: hashlib, dataclasses, app.integration.
Connection: Protects canonical hashing and service-result serialization used
by compliance, blockchain, audit, and integrated pipeline records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pytest

from app.integration.adapters import AdapterError, serialise_result
from app.integration.service import canonical_hash, canonical_json


@dataclass
class ExampleResult:
    passed: bool
    status: str
    results: dict[str, object]
    failed_stage: str | None = None


def test_canonical_json_is_deterministic() -> None:
    first = {
        "chip_id": "CHIP-001",
        "risk": 0.12,
        "metadata": {"supplier": "Trusted", "country": "GB"},
    }

    second = {
        "metadata": {"country": "GB", "supplier": "Trusted"},
        "risk": 0.12,
        "chip_id": "CHIP-001",
    }

    assert canonical_json(first) == canonical_json(second)


def test_canonical_json_has_no_nonessential_whitespace() -> None:
    encoded = canonical_json({"b": 2, "a": 1})

    assert encoded == '{"a":1,"b":2}'


def test_canonical_hash_matches_sha256() -> None:
    record = {
        "scan_id": "SCAN-001",
        "decision": "DEPLOY",
    }

    expected = hashlib.sha256(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    assert canonical_hash(record) == expected


def test_canonical_hash_is_lowercase_sha256() -> None:
    digest = canonical_hash({"value": "test"})

    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(character in "0123456789abcdef" for character in digest)


def test_dataclass_service_result_is_serialised() -> None:
    result = serialise_result(
        ExampleResult(
            passed=True,
            status="PASSED",
            results={"yosys": {"passed": True}},
        )
    )

    assert result["passed"] is True
    assert result["status"] == "PASSED"
    assert result["results"]["yosys"]["passed"] is True


def test_dictionary_service_result_is_preserved() -> None:
    result = {
        "passed": True,
        "classification": "CLEAN",
    }

    assert serialise_result(result) is result


def test_unsupported_service_result_fails_closed() -> None:
    with pytest.raises(AdapterError):
        serialise_result(object())
