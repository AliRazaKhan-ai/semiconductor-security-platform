"""Purpose: Assert the reference design is pinned and a modified one is refused.
Directory: tests/hardware.
Dependencies: pytest, hashlib, json.
Connection: Guards T-12 design integrity. Reference-differential synthesis trusts the
reference RTL absolutely; a modified reference would become the new baseline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.hardware.yosys.adapter import YosysAdapter

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "hardware_lab/rtl/reference/semisecure_demo_core.sv"
CONFIG = ROOT / "configs/hardware/yosys.json"


def _policy() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    return config.get("yosys", config)


@pytest.mark.security
def test_configuration_pins_the_current_reference() -> None:
    trusted = _policy().get("trusted_reference_digests")
    assert trusted, "no trusted reference digest is pinned in yosys.json"

    actual = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    assert actual in trusted, (
        "The reference RTL has changed without its pinned digest. Update "
        "trusted_reference_digests in the same commit, deliberately."
    )


@pytest.mark.security
def test_an_untrusted_reference_is_refused_before_synthesis(tmp_path) -> None:
    tampered = tmp_path / "semisecure_demo_core.sv"
    tampered.write_text(REFERENCE.read_text(encoding="utf-8") + "\n// modified\n")

    policy = dict(_policy())
    adapter = YosysAdapter(policy)

    with pytest.raises(Exception, match="trusted digest"):
        adapter.analyse_against_reference(REFERENCE, tampered, "semisecure_demo_core")
