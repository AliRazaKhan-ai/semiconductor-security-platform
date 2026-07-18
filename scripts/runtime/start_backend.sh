#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

source venv/bin/activate

set -a
source .env
set +a

mkdir -p runtime

PID_FILE="$PROJECT_ROOT/runtime/backend.pid"
LOG_FILE="$PROJECT_ROOT/runtime/backend.log"

if curl -fsS http://127.0.0.1:5000/health/live \
    >/dev/null 2>&1
then
    echo "Backend is already running."
    exit 0
fi

if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE")"

    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill -TERM "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi

    rm -f "$PID_FILE"
fi

nohup ./venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 1 \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    wsgi:app \
    >"$LOG_FILE" 2>&1 &

BACKEND_PID="$!"
echo "$BACKEND_PID" >"$PID_FILE"

for attempt in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:5000/health/live \
        >/dev/null 2>&1
    then
        echo "Backend started successfully."
        echo "PID: $BACKEND_PID"
        echo "Dashboard: http://127.0.0.1:5000/dashboard"
        echo "Log: $LOG_FILE"
        exit 0
    fi

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "ERROR: backend terminated during startup."
        tail -150 "$LOG_FILE"
        exit 1
    fi

    sleep 1
done

echo "ERROR: backend did not become healthy."
tail -150 "$LOG_FILE"
exit 1
