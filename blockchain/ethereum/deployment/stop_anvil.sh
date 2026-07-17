#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PID_FILE="$PROJECT_ROOT/runtime/anvil.pid"
STATE_FILE="$PROJECT_ROOT/data/blockchain/anvil-state.json"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No Anvil PID file exists."
    exit 0
fi

ANVIL_PID="$(cat "$PID_FILE")"

if ! kill -0 "$ANVIL_PID" 2>/dev/null; then
    echo "Anvil process $ANVIL_PID is not running."
    rm -f "$PID_FILE"
    exit 0
fi

kill -TERM "$ANVIL_PID"

for attempt in $(seq 1 20); do
    if ! kill -0 "$ANVIL_PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Anvil stopped successfully."

        if [[ -f "$STATE_FILE" ]]; then
            echo "State saved: $STATE_FILE"
        else
            echo "WARNING: state file was not created."
        fi

        exit 0
    fi

    sleep 1
done

echo "Anvil did not stop gracefully; forcing termination."
kill -KILL "$ANVIL_PID" 2>/dev/null || true
rm -f "$PID_FILE"
