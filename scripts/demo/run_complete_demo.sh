#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

export PATH="$HOME/hyperledger/fabric-samples/bin:$HOME/.foundry/bin:$PATH"

if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
fi

set -a
[[ -f .env ]] && source .env
set +a

echo "========================================"
echo " SemiSecure Complete Phase 3 Demo"
echo "========================================"

echo "[1/8] Checking Docker"
docker info >/dev/null

for container in \
    orderer.example.com \
    peer0.org1.example.com \
    peer0.org2.example.com \
    ca_orderer \
    ca_org1 \
    ca_org2
do
    if docker inspect "$container" >/dev/null 2>&1; then
        docker start "$container" >/dev/null 2>&1 || true
    fi
done

docker ps -a \
    --filter "name=dev-peer" \
    --format '{{.Names}}' \
    | xargs -r docker start \
    >/dev/null 2>&1 || true

echo "[2/8] Starting persistent Ethereum node"
./blockchain/ethereum/deployment/start_anvil.sh

if ! ./blockchain/ethereum/deployment/verify_contract.sh; then
    echo "Ethereum contract missing after startup; redeploying."

    ./blockchain/ethereum/deployment/deploy_contract.sh
    ./blockchain/ethereum/deployment/verify_contract.sh
fi

echo "[3/8] Checking Python sources"
find app tests \
    -type f \
    -name "*.py" \
    -print0 \
    | xargs -0 ./venv/bin/python -m py_compile

./venv/bin/python -m py_compile \
    manage.py \
    run.py

echo "[4/8] Running automated tests"
./venv/bin/python -m pytest -q

echo "[5/8] Checking services"
./venv/bin/python manage.py system-status \
    >runtime/demo-system-status.json

echo "[6/8] Running the integrated pipeline over all eight scenarios"
# pipeline-all routes to Phase3Orchestrator and returns lookup-table verdicts.
# run_integrated_demo.sh runs IntegratedPipelineService and mints per chip,
# because a PUF challenge is single-use and attestation expires in 300 seconds.
./scripts/demo/run_integrated_demo.sh --all \
    | tee runtime/demo-pipeline-results.txt

echo "[7/8] Verifying event store"
./venv/bin/python manage.py verify-event-store \
    | tee runtime/demo-event-store-verification.json

echo "[8/8] Listing quarantine records"
./venv/bin/python manage.py quarantine-list \
    | tee runtime/demo-quarantine.json

echo
echo "========================================"
echo " Phase 3 demonstration completed"
echo "========================================"
echo "Results: runtime/demo-pipeline-results.json"
echo "Status:  runtime/demo-system-status.json"
echo "Audit:   runtime/demo-event-store-verification.json"
echo "Quarantine: runtime/demo-quarantine.json"
