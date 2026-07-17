from __future__ import annotations

import pytest

from app.exceptions import ValidationError
from app.security.schema_validation import validate_payload


def test_scan_schema_accepts_valid_payload() -> None:
    validate_payload("scan_submission", {"chip_id": "CHIP-001", "evidence": {"source": "terminal"}})


def test_scan_schema_rejects_path_traversal_identifier() -> None:
    with pytest.raises(ValidationError):
        validate_payload("scan_submission", {"chip_id": "../../etc/passwd", "evidence": {"source": "terminal"}})

