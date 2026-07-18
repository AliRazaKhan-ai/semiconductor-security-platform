#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_FILE="$PROJECT_ROOT/runtime/backend.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No backend PID file exists."
    exit 0
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID"

    for attempt in $(seq 1 20); do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "Backend stopped."
            exit 0
        fi

        sleep 1
    done

    kill -KILL "$PID" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "Backend stopped."
