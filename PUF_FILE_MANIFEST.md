# Production PUF Simulator File Manifest

## Runtime modules

| File | Purpose | Direct dependencies | Connection | Ubuntu command |
|---|---|---|---|---|
| `app/hardware/puf/__init__.py` | Public PUF package exports | Adapter, config, schemas, simulator | Import surface for pipeline and terminal | `python -m compileall -q app/hardware/puf/__init__.py` |
| `app/hardware/puf/adapter.py` | Application facade for enrollment, challenge issue, response simulation and verification | Config, repositories, simulator, verifier, environment secret | Used by terminal CLI and PUF pipeline stage | `SEMISURE_PUF_MASTER_SECRET='minimum-32-byte-secret-value' python -m app.hardware.puf.cli health` |
| `app/hardware/puf/cli.py` | Terminal-only operational interface | Argparse, adapter, JSON schemas | Terminal controls enrollment and authentication; dashboard remains read-only | `python -m app.hardware.puf.cli --help` |
| `app/hardware/puf/config.py` | Strict PUF JSON configuration loader | Dataclasses, JSON config store | Creates validated parameters for all PUF algorithms | `python -c "from pathlib import Path; from app.hardware.puf.config import load_puf_config; print(load_puf_config(Path('configs/hardware/puf.json')).fingerprint)"` |
| `app/hardware/puf/crypto.py` | HMAC PRNG, hashing, key derivation and protected template sealing | Python cryptographic standard library | Supplies deterministic process variation, signed challenges and protected references | `python -m compileall -q app/hardware/puf/crypto.py` |
| `app/hardware/puf/exceptions.py` | Typed fail-closed PUF errors | PlatformError | Propagates configuration, integrity, replay and authentication failures | `python -m compileall -q app/hardware/puf/exceptions.py` |
| `app/hardware/puf/repository.py` | JSON enrollment repository and append-only challenge ledger | JSON, atomic filesystem writes, FileLock | Stores signed profiles and prevents challenge replay without SQL | `python -m compileall -q app/hardware/puf/repository.py` |
| `app/hardware/puf/schemas.py` | Immutable challenge, response, profile and result contracts | Dataclasses, HMAC validation | Shared across simulator, verifier, CLI and pipeline | `python -m compileall -q app/hardware/puf/schemas.py` |
| `app/hardware/puf/simulator.py` | Hybrid Ring Oscillator and Delay Chain physical model | Config, HMAC PRNG, schemas, stability | Produces realistic noisy responses under temperature, voltage and aging drift | `python -m compileall -q app/hardware/puf/simulator.py` |
| `app/hardware/puf/stability.py` | Majority vote, reliability masks, Hamming distance and noise-distance algorithms | Math, config, environment schema | Used during enrollment and authentication | `python -m compileall -q app/hardware/puf/stability.py` |
| `app/hardware/puf/verifier.py` | Enrollment, identity hashing, drift-tolerant verification and clone rejection | Crypto, simulator, stability, schemas | Produces signed profiles and final PUF authentication result | `python -m compileall -q app/hardware/puf/verifier.py` |
| `app/pipeline/stages/puf_stage.py` | Fail-closed pipeline integration | PUFAdapter, JSON Event Store, SocketIO publisher contract | Runs before OpenTitan and stops the pipeline on any PUF failure | `python -m compileall -q app/pipeline/stages/puf_stage.py` |

## Configuration and documentation

| File | Purpose | Direct dependencies | Connection | Ubuntu command |
|---|---|---|---|---|
| `configs/hardware/puf.json` | Production physical, environmental, enrollment and authentication parameters | JSON | Loaded by PUFAdapter; contains no secret | `python -m json.tool configs/hardware/puf.json >/dev/null` |
| `schemas/chips/puf_enrollment.schema.json` | JSON Schema for signed enrollment profiles | JSON Schema 2020-12 | Validates stored PUF profile shape | `python -m json.tool schemas/chips/puf_enrollment.schema.json >/dev/null` |
| `docs/architecture/PUF_SIMULATOR.md` | Complete algorithm explanation and security rationale | None | Viva and implementation reference | `less docs/architecture/PUF_SIMULATOR.md` |
| `PUF_FILE_MANIFEST.md` | Per-file purpose, dependencies, connection and commands | None | Implementation inventory | `less PUF_FILE_MANIFEST.md` |

## Automated tests

| File | Purpose | Direct dependencies | Connection | Ubuntu command |
|---|---|---|---|---|
| `tests/puf_test_config.py` | Compact representative test configuration | Dataclasses, production PUF config | Keeps automated tests fast while retaining hybrid behaviour | `python -m compileall -q tests/puf_test_config.py` |
| `tests/hardware_simulation/test_puf_simulator.py` | Physical behaviour tests | Pytest, simulator | Checks stability, uniqueness, drift and challenge composition | `pytest -q tests/hardware_simulation/test_puf_simulator.py` |
| `tests/unit/test_puf_verifier.py` | Enrollment and authentication tests | Pytest, adapter | Checks identity, drift tolerance, replay and clone rejection | `pytest -q tests/unit/test_puf_verifier.py` |
| `tests/integration/test_puf_stage.py` | Event Store and pipeline tests | Pytest, PUFStage, EventStore | Confirms durable events, SocketIO publication and fail-closed flow | `pytest -q tests/integration/test_puf_stage.py` |
| `tests/security/test_puf_anti_cloning.py` | Security-control tests | Pytest, adapter | Checks challenge tampering, consumed failed attempts and sealed references | `pytest -q tests/security/test_puf_anti_cloning.py` |

## Generation and validation

| File | Purpose | Direct dependencies | Connection | Ubuntu command |
|---|---|---|---|---|
| `scripts/generate_production_puf.sh` | Recreates every PUF file one-by-one using `cat > file <<'EOF'` | Bash | Required reproducible file-creation method | `chmod +x scripts/generate_production_puf.sh && ./scripts/generate_production_puf.sh semiconductor_security_platform` |
| `scripts/validate_production_puf.sh` | Compiles, tests and performs genuine/clone production smoke validation | Bash, Python, pytest | Final quality gate | `chmod +x scripts/validate_production_puf.sh && ./scripts/validate_production_puf.sh` |

## Terminal workflow

```bash
export SEMISURE_PUF_MASTER_SECRET='replace-through-runtime-secret-manager-with-at-least-32-bytes'

python -m app.hardware.puf.cli enroll \
  --device-id CHIP-001

python -m app.hardware.puf.cli challenge \
  --device-id CHIP-001 \
  --output runtime/puf/challenge.json

python -m app.hardware.puf.cli respond \
  --device-id CHIP-001 \
  --challenge runtime/puf/challenge.json \
  --output runtime/puf/response.json \
  --temperature-c 25 \
  --voltage-v 1.0

python -m app.hardware.puf.cli authenticate \
  --device-id CHIP-001 \
  --challenge runtime/puf/challenge.json \
  --response runtime/puf/response.json
```

The quoted value above is an instruction to supply a runtime secret; it is not a usable project secret and is never stored by the application.
