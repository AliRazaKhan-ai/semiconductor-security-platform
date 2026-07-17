#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ETHEREUM_ROOT="$PROJECT_ROOT/blockchain/ethereum"
RPC_URL="${SEMISURE_ETHEREUM_RPC_URL:-http://127.0.0.1:8545}"
PRIVATE_KEY="${SEMISURE_ETHEREUM_PRIVATE_KEY:-}"
DEPLOYMENT_FILE="$ETHEREUM_ROOT/deployment/deployment.json"
RAW_FILE="$ETHEREUM_ROOT/deployment/deployment.raw.json"

export PATH="$HOME/.foundry/bin:$PATH"

if [[ -z "$PRIVATE_KEY" ]]; then
    echo "ERROR: SEMISURE_ETHEREUM_PRIVATE_KEY is not configured."
    exit 1
fi

curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
    "$RPC_URL" >/dev/null

forge build --root "$ETHEREUM_ROOT"

forge create \
    --root "$ETHEREUM_ROOT" \
    --rpc-url "$RPC_URL" \
    --private-key "$PRIVATE_KEY" \
    --broadcast \
    --json \
    contracts/HashAnchor.sol:HashAnchor \
    > "$RAW_FILE"

python - "$RAW_FILE" "$DEPLOYMENT_FILE" <<'PY'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

raw_path = Path(sys.argv[1])
destination = Path(sys.argv[2])

raw = raw_path.read_text(encoding="utf-8").strip()
data = json.loads(raw)

address = (
    data.get("deployedTo")
    or data.get("deployed_to")
    or data.get("contractAddress")
    or data.get("contract_address")
)

transaction_hash = (
    data.get("transactionHash")
    or data.get("transaction_hash")
)

if not address:
    raise SystemExit(
        f"Deployment output did not contain a contract address: {data}"
    )

result = {
    "schema_version": "1.0",
    "network": "anvil-local",
    "chain_id": 31337,
    "rpc_url": "http://127.0.0.1:8545",
    "contract": "HashAnchor",
    "contract_address": address,
    "deployment_transaction_hash": transaction_hash,
    "deployed_at_utc": datetime.now(UTC).isoformat(),
}

destination.write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)

print(address)
PY
