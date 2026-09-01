from __future__ import annotations

from pathlib import Path

from app.hardware.common import require_file

_REQUIRED_VERIFICATION_TOKENS = (
    "SEMISURE_PASS",
    "ASSERTIONS=",
    "CYCLES=",
    "RESET_COMPLETED",
    "REQUIRED_CHECKS_PASSED=1",
)


def validate_testbench(path: Path) -> Path:
    path = require_file(path, "verilator")
    text = path.read_text(encoding="utf-8", errors="replace")

    if "$finish" not in text and "$fatal" not in text:
        raise ValueError(
            "testbench must contain an explicit $finish or $fatal"
        )

    missing = [
        token
        for token in _REQUIRED_VERIFICATION_TOKENS
        if token not in text
    ]

    if missing:
        raise ValueError(
            "testbench must implement verification summary markers: "
            + ", ".join(missing)
        )

    return path
