# Installation Guide

## 1. Supported deployment methods

- Native Ubuntu with Python virtual environment.
- Native Ubuntu managed by systemd.
- Docker image.
- Docker Compose with persistent data mounts.

## 2. Prerequisites

Recommended host:

- Ubuntu 22.04 or later;
- Python 3.12;
- 8 GB RAM minimum, 16 GB recommended;
- 20 GB free disk space for source, environments, models, containers, blockchain state, and audit data;
- Docker 24+ and Docker Compose v2 for container and blockchain workflows;
- Git, `curl`, `zip`, build tools, and OpenSSL libraries.

Install base packages:

```bash
sudo apt-get update
sudo apt-get install -y \
  git curl zip unzip build-essential \
  python3.12 python3.12-venv python3-pip \
  libffi-dev libssl-dev libgomp1
```

## 3. Clone the repository

```bash
git clone https://github.com/AliRazaKhan-ai/semiconductor-security-platform.git
cd semiconductor-security-platform
```

For a non-default branch:

```bash
git fetch origin
git checkout phase-4-production-hardening
```

## 4. Native Python installation

```bash
python3.12 -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Confirm imports:

```bash
python - <<'PY'
import flask
import flask_socketio
import numpy
import sklearn
import torch
print("Core imports successful.")
PY
```

TensorFlow is available only for supported Python versions as defined in `requirements.txt`.

## 5. Environment variables

Use the generated deployment helper when installed:

```bash
scripts/deployment/generate_env.sh
```

This creates `.env.production`. Keep it outside Git.

Typical variables:

```dotenv
SEMISURE_ENV=production
SEMISURE_BIND_HOST=0.0.0.0
SEMISURE_PORT=5000
SEMISURE_WORKERS=1
SEMISURE_LOG_LEVEL=INFO
SEMISURE_CONFIG_ROOT=/absolute/path/configs
SEMISURE_DATA_ROOT=/absolute/path/data
SEMISURE_RUNTIME_ROOT=/absolute/path/runtime
SEMISURE_MODEL_ROOT=/absolute/path/models
SEMISURE_FABRIC_ENABLED=true
SEMISURE_ETHEREUM_ENABLED=true
SEMISURE_ETHEREUM_RPC_URL=http://localhost:8545
```

Never store private keys, passwords, tokens, mnemonics, or Fabric identities in committed environment files.

## 6. Prepare runtime directories

```bash
mkdir -p \
  data/event_store \
  data/indexes \
  data/snapshots \
  data/audit \
  data/archive \
  data/compliance/decisions \
  data/compliance/government_audit \
  data/blockchain/ethereum_receipts \
  runtime/locks \
  runtime/logs \
  runtime/pids
```

## 7. Validate the codebase

```bash
python -m py_compile app/factory.py manage.py
python -m pytest -q
```

A targeted smoke test:

```bash
python -m pytest \
  tests/dashboard \
  tests/static \
  tests/api \
  tests/pipeline/test_permanent_rejection_routing.py \
  -q
```

## 8. Start the native backend

Using the existing runtime script:

```bash
./scripts/runtime/start_backend.sh
```

Or foreground production process:

```bash
scripts/deployment/native_run.sh
```

Verify:

```bash
curl -fsS http://localhost:5000/health/live
curl -fsS http://localhost:5000/health/ready | python -m json.tool
```

Dashboard:

```text
http://localhost:5000/dashboard
```

## 9. Install systemd service

```bash
scripts/deployment/install_systemd.sh
```

Operations:

```bash
sudo systemctl status semisecure.service
sudo systemctl restart semisecure.service
sudo systemctl stop semisecure.service
journalctl -u semisecure.service -f
```

## 10. Docker installation

Install Docker using Ubuntu's supported package workflow, then verify:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

Build the application:

```bash
scripts/deployment/docker_build.sh
```

Run with Compose:

```bash
scripts/deployment/docker_up.sh
```

Check:

```bash
docker compose ps
scripts/deployment/health_check.sh
```

Logs:

```bash
scripts/deployment/docker_logs.sh
```

Stop:

```bash
scripts/deployment/docker_down.sh
```

When Ethereum runs on the host and the application runs in Docker:

```dotenv
SEMISURE_ETHEREUM_RPC_URL=http://host.docker.internal:8545
```

## 11. Blockchain services

The exact Fabric and Ethereum startup commands depend on project scripts and configuration. Use the project's blockchain startup/verification scripts before running full provenance tests.

Confirm:

```bash
curl -fsS http://localhost:5000/api/v1/blockchain/status \
  | python -m json.tool
```

A blockchain service may report degraded status while the core API remains available. Approval policy should still treat required provenance failures according to configuration.

## 12. Model readiness

Verify model files and manifests under `models/`. Run model-specific tests before live demonstrations.

Typical checks:

```bash
find models -maxdepth 3 -type f -printf '%p %s bytes\n' | sort
python -m pytest tests/ai -q
```


## 13. Run reference scans

```bash
scripts/deployment/run_scan.sh "$PWD" data/chips/chip_01_good.json
scripts/deployment/run_scan.sh "$PWD" data/chips/chip_06_counterfeit.json
```

Confirm results through the API:

```bash
curl -fsS http://localhost:5000/api/v1/scans/latest \
  | python -m json.tool
```

## 14. Final installation checklist

- [ ] Virtual environment installs without errors.
- [ ] Required model files exist.
- [ ] Event store, indexes, snapshots, audit, and lock directories are writable.
- [ ] `/health/live` responds.
- [ ] `/health/ready` reports ready.
- [ ] Dashboard loads without console errors.
- [ ] At least one approved and one rejected reference scan complete.
- [ ] Fabric status is known.
- [ ] Ethereum status is known.
- [ ] `.env.production` is ignored by Git.
- [ ] Runtime data and keys are backed up securely.
