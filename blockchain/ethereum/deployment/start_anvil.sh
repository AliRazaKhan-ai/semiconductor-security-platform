#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/runtime/anvil.log"
PID_FILE="$PROJECT_ROOT/runtime/anvil.pid"
STATE_FILE="$PROJECT_ROOT/data/blockchain/anvil-state.json"
BACKUP_ROOT="$PROJECT_ROOT/backups/blockchain_state"
RPC_URL="http://127.0.0.1:8545"

export PATH="$HOME/.foundry/bin:$PATH"

mkdir -p \
  "$PROJECT_ROOT/runtime" \
  "$PROJECT_ROOT/data/blockchain" \
  "$BACKUP_ROOT"

if ! command -v anvil >/dev/null 2>&1; then
    echo "ERROR: anvil is not installed or is unavailable in PATH."
    exit 1
fi

rpc_ready() {
    curl -fsS \
        -X POST \
        -H "Content-Type: application/json" \
        --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
        "$RPC_URL" \
        >/dev/null 2>&1
}

validate_state() {
    [[ ! -f "$STATE_FILE" ]] && return 0

    python -m json.tool \
        "$STATE_FILE" \
        >/dev/null 2>&1
}

if rpc_ready; then
    echo "Anvil is already running on port 8545."
    exit 0
fi

ANVIL_TEMP_DIR="$HOME/.foundry/anvil/tmp"

echo "Cleaning stale Anvil temporary state files..."

rm -rf "$ANVIL_TEMP_DIR"
mkdir -p "$ANVIL_TEMP_DIR"
chmod 700 "$ANVIL_TEMP_DIR"

if ! validate_state; then
    TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
    CORRUPT_BACKUP="$BACKUP_ROOT/anvil-state-corrupt-$TIMESTAMP.json"

    cp "$STATE_FILE" "$CORRUPT_BACKUP"
    rm -f "$STATE_FILE"

    echo "WARNING: corrupted Anvil state was backed up:"
    echo "$CORRUPT_BACKUP"
    echo "Starting Anvil with a clean state."
fi

ANVIL_ARGS=(
    --host 127.0.0.1
    --port 8545
    --chain-id 31337
    --mnemonic "test test test test test test test test test test test junk"
    --block-time 1
    --state "$STATE_FILE"
    --state-interval 300
)

nohup anvil \
    "${ANVIL_ARGS[@]}" \
    >"$LOG_FILE" 2>&1 &

ANVIL_PID="$!"
echo "$ANVIL_PID" >"$PID_FILE"

for attempt in $(seq 1 30); do
    if rpc_ready; then
        echo "Anvil started successfully."
        echo "PID: $ANVIL_PID"
        echo "RPC: $RPC_URL"
        echo "State: $STATE_FILE"
        echo "Log: $LOG_FILE"
        exit 0
    fi

    sleep 1
done

echo "ERROR: Anvil did not become ready within 30 seconds."

if kill -0 "$ANVIL_PID" 2>/dev/null; then
    kill "$ANVIL_PID" 2>/dev/null || true
fi

tail -100 "$LOG_FILE" 2>/dev/null || true
exit 1
