#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

export PATH="$HOME/hyperledger/fabric-samples/bin:$HOME/.foundry/bin:$PATH"

if [[ ! -f venv/bin/activate ]]; then
    echo "ERROR: venv/bin/activate does not exist."
    exit 1
fi

source venv/bin/activate

set -a
source .env
set +a

mkdir -p runtime

echo "[1/7] Checking Docker"

if docker info >/dev/null 2>&1
then
    echo "  Docker is already running."
else
    echo "  Docker is not running; requesting permission to start it."

    if ! sudo systemctl start docker
    then
        echo "ERROR: Docker could not be started."
        exit 1
    fi

    for attempt in $(seq 1 20)
    do
        if docker info >/dev/null 2>&1
        then
            echo "  Docker started."
            break
        fi

        if [[ "$attempt" -eq 20 ]]
        then
            echo "ERROR: Docker did not become ready."
            exit 1
        fi

        sleep 1
    done
fi

echo "[2/7] Starting and verifying Fabric"

FABRIC_NETWORK_ROOT="$HOME/hyperledger/fabric-samples/test-network"

required_fabric_containers=(
    orderer.example.com
    peer0.org1.example.com
    peer0.org2.example.com
)

fabric_containers_missing=false

for container in "${required_fabric_containers[@]}"
do
    if ! docker inspect "$container" >/dev/null 2>&1
    then
        fabric_containers_missing=true
        break
    fi
done

if [[ "$fabric_containers_missing" == "true" ]]
then
    echo "  Core Fabric containers are missing; restoring them."

    if [[ ! -x "$FABRIC_NETWORK_ROOT/network.sh" ]]
    then
        echo "ERROR: Fabric network.sh was not found."
        exit 1
    fi

    (
        cd "$FABRIC_NETWORK_ROOT"

        export PATH="$HOME/hyperledger/fabric-samples/bin:$PATH"
        export FABRIC_CFG_PATH="$HOME/hyperledger/fabric-samples/config"

        ./network.sh up -ca
    )
else
    for container in "${required_fabric_containers[@]}"
    do
        docker start "$container" >/dev/null 2>&1 || true
        echo "  started: $container"
    done
fi

docker ps -a \
    --filter "name=dev-peer" \
    --format '{{.Names}}' \
    | xargs -r docker start \
    >/dev/null 2>&1 || true

echo "  Waiting for Fabric chaincode runtime"

for attempt in $(seq 1 30)
do
    if docker ps \
        --format '{{.Names}}' \
        | grep -q 'semiconductor-provenance_1.2'
    then
        echo "  Chaincode runtime is running."
        break
    fi

    if [[ "$attempt" -eq 30 ]]
    then
        echo "  Chaincode container is not yet visible."
        echo "  The verification step will continue retrying."
        break
    fi

    sleep 1
done

echo "[3/7] Waiting for Fabric peer"

for attempt in $(seq 1 30)
do
    if timeout 1 bash -c '</dev/tcp/127.0.0.1/7051' \
        >/dev/null 2>&1
    then
        echo "  Fabric peer is reachable on port 7051"
        break
    fi

    if [[ "$attempt" -eq 30 ]]; then
        echo "ERROR: Fabric peer did not become reachable."
        docker ps \
            --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
        exit 1
    fi

    sleep 1
done

echo "  Verifying existing Fabric channel and chaincode"

if ! ./scripts/runtime/verify_fabric.sh
then
    echo
    echo "ERROR: Fabric containers are running, but the existing"
    echo "channel or committed chaincode could not be verified."
    echo
    echo "Do not run createChannel or deployCC automatically."
    echo "Inspect the ledger before attempting recovery."
    exit 1
fi

echo "[4/7] Starting Ethereum"

./blockchain/ethereum/deployment/start_anvil.sh

if ! ./blockchain/ethereum/deployment/verify_contract.sh
then
    echo "  Contract is unavailable; deploying it now."
    ./blockchain/ethereum/deployment/deploy_contract.sh
    ./blockchain/ethereum/deployment/verify_contract.sh
fi

echo "[5/7] Starting backend and dashboard"

./scripts/runtime/start_backend.sh

echo "[6/7] Checking services"

curl -fsS http://127.0.0.1:5000/health/live \
    | python -m json.tool

curl -fsS http://127.0.0.1:5000/health/ready \
    | python -m json.tool

curl -fsS http://127.0.0.1:5000/api/v1/blockchain/status \
    | python -m json.tool

curl -fsS http://127.0.0.1:5000/api/v1/compliance/status \
    | python -m json.tool

curl -fsS http://127.0.0.1:5000/api/v1/hardware/status \
    | python -m json.tool

echo "[6.5/7] Checking strict hardware evidence"

if ./venv/bin/python scripts/integration/check_hardware_manifests.py     >runtime/hardware-manifest-status.json 2>&1
then
    echo "  Strict hardware manifests: READY"
else
    echo "  Strict hardware manifests: NOT AVAILABLE"
    echo "  Examination simulation pipeline remains available."
    echo "  Details: runtime/hardware-manifest-status.json"
fi

echo "[7/7] Checking dashboard"

ROOT_HTTP="$(
    curl -sS \
        -o /tmp/semisecure-root.html \
        -w '%{http_code}' \
        http://127.0.0.1:5000/
)"

DASHBOARD_HTTP="$(
    curl -sS \
        -o /tmp/semisecure-dashboard.html \
        -w '%{http_code}' \
        http://127.0.0.1:5000/dashboard
)"

if [[ "$ROOT_HTTP" != "200" || "$DASHBOARD_HTTP" != "200" ]]
then
    echo "ERROR: dashboard route check failed."
    echo "Root HTTP: $ROOT_HTTP"
    echo "Dashboard HTTP: $DASHBOARD_HTTP"
    tail -150 runtime/backend.log 2>/dev/null || true
    exit 1
fi

echo
echo "=============================================="
echo " SemiSecure services are online"
echo "=============================================="
echo "Dashboard:  http://127.0.0.1:5000/"
echo "Readiness:  http://127.0.0.1:5000/health/ready"
echo "System:     http://127.0.0.1:5000/api/v1/system/status"
echo "Blockchain: http://127.0.0.1:5000/api/v1/blockchain/status"
echo "Backend log: $PROJECT_ROOT/runtime/backend.log"
