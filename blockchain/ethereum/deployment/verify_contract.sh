#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEPLOYMENT_FILE="$PROJECT_ROOT/blockchain/ethereum/deployment/deployment.json"
RPC_URL="${SEMISURE_ETHEREUM_RPC_URL:-http://127.0.0.1:8545}"

export PATH="$HOME/.foundry/bin:$PATH"

if [[ ! -f "$DEPLOYMENT_FILE" ]]; then
    echo "ERROR: deployment.json was not found."
    exit 1
fi

CONTRACT_ADDRESS="$(
python - "$DEPLOYMENT_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["contract_address"])
PY
)"

CODE="$(cast code "$CONTRACT_ADDRESS" --rpc-url "$RPC_URL")"

if [[ "$CODE" == "0x" || -z "$CODE" ]]; then
    echo "ERROR: no contract code exists at $CONTRACT_ADDRESS"
    exit 1
fi

CHAIN_ID="$(cast chain-id --rpc-url "$RPC_URL")"

echo "Contract address: $CONTRACT_ADDRESS"
echo "Chain ID: $CHAIN_ID"
echo "Contract bytecode present: yes"
echo "HASH ANCHOR CONTRACT VERIFIED"
