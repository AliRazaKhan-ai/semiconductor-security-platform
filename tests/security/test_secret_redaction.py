from __future__ import annotations

from app.observability.logging.redaction import REDACTED, redact


def test_nested_sensitive_fields_are_redacted() -> None:
    result = redact(
        {"chip": "CHIP-001", "private_key": "secret", "nested": {"puf_response": "raw"}},
        {"private_key", "puf_response"},
    )
    assert result["chip"] == "CHIP-001"
    assert result["private_key"] == REDACTED
    assert result["nested"]["puf_response"] == REDACTED

