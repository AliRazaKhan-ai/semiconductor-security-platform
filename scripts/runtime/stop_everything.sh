#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

./scripts/runtime/stop_backend.sh || true

./blockchain/ethereum/deployment/stop_anvil.sh || true

docker stop \
    orderer.example.com \
    peer0.org1.example.com \
    peer0.org2.example.com \
    ca_orderer \
    ca_org1 \
    ca_org2 \
    >/dev/null 2>&1 || true

docker ps -a \
    --filter "name=dev-peer" \
    --format '{{.Names}}' \
    | xargs -r docker stop \
    >/dev/null 2>&1 || true

echo "SemiSecure runtime services stopped."
