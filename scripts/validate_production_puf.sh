#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
cd "$ROOT"

python -m compileall -q app/hardware/puf app/pipeline/stages/puf_stage.py
pytest -q \
  tests/hardware_simulation/test_puf_simulator.py \
  tests/unit/test_puf_verifier.py \
  tests/integration/test_puf_stage.py \
  tests/security/test_puf_anti_cloning.py

python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.config import load_puf_config
from app.hardware.puf.schemas import PUFEnvironment

config = load_puf_config(Path("configs/hardware/puf.json"))
assert config.total_response_bits == 96
assert config.ring_oscillator.response_bits == 48
assert config.delay_chain.response_bits == 48

with TemporaryDirectory() as temporary:
    adapter = PUFAdapter(
        config=config,
        master_secret=b"validation-master-secret-000000000000000000000000000",
        project_root=Path(temporary),
    )
    adapter.enroll_device("VALIDATION-CHIP-001")

    genuine_challenge = adapter.issue_challenge("VALIDATION-CHIP-001")
    genuine_response = adapter.simulate_response(
        "VALIDATION-CHIP-001",
        genuine_challenge,
        PUFEnvironment(temperature_c=85.0, voltage_v=1.05),
    )
    genuine_result = adapter.authenticate(
        "VALIDATION-CHIP-001",
        genuine_challenge,
        genuine_response,
    )
    assert genuine_result.accepted

    clone_challenge = adapter.issue_challenge("VALIDATION-CHIP-001")
    clone_response = adapter.simulator("VALIDATION-CLONE-001").respond(
        clone_challenge,
        PUFEnvironment(),
        sample_count=config.authentication.response_samples,
    )
    clone_result = adapter.authenticate(
        "VALIDATION-CHIP-001",
        clone_challenge,
        clone_response,
    )
    assert not clone_result.accepted
    assert "RESPONSE_MISMATCH" in clone_result.reasons

print("production PUF validation passed")
PY

if grep -RInE 'TODO|FIXME|NotImplemented|placeholder|pseudo code' \
  app/hardware/puf app/pipeline/stages/puf_stage.py; then
  echo "Forbidden incomplete implementation marker detected" >&2
  exit 1
fi
