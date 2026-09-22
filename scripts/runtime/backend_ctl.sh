#!/usr/bin/env bash
# Purpose: Start, stop or restart the backend through whichever manager owns it.
# Directory: scripts/runtime
#
# The backend can run under systemd (deployment/systemd/semisecure-backend.service)
# or be launched by start_backend.sh. Both bind 127.0.0.1:5000, so the two must
# never run together. When the unit is enabled, systemd owns the backend and this
# script only talks to systemctl; otherwise it uses the scripts.
#
#   backend_ctl.sh start | stop | restart | status

set -Eeuo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

UNIT="semisecure-backend"
HEALTH="http://127.0.0.1:5000/health/ready"

managed_by_systemd() {
    systemctl is-enabled --quiet "$UNIT" 2>/dev/null
}

wait_until_answering() {
    # The first request after a start pays gevent initialisation, measured at 6 to
    # 18 seconds, so allow a minute. 503 counts as answering: it means degraded,
    # with the failed subsystems named, not unreachable.
    for _ in $(seq 1 60); do
        code="$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$HEALTH" || true)"
        if [[ "$code" == "200" || "$code" == "503" ]]; then
            echo "  backend answering (HTTP $code)"
            return 0
        fi
        sleep 1
    done
    echo "  backend did not answer within 60 seconds"
    return 1
}

case "${1:-}" in
start)
    if managed_by_systemd; then
        echo "  backend is managed by systemd"
        sudo systemctl start "$UNIT"
    else
        ./scripts/runtime/start_backend.sh
    fi
    wait_until_answering
    ;;
stop)
    if managed_by_systemd; then
        sudo systemctl stop "$UNIT"
    else
        ./scripts/runtime/stop_backend.sh || true
    fi
    ;;
restart)
    if managed_by_systemd; then
        echo "  backend is managed by systemd"
        sudo systemctl restart "$UNIT"
    else
        ./scripts/runtime/stop_backend.sh || true
        ./scripts/runtime/start_backend.sh
    fi
    wait_until_answering
    ;;
status)
    if managed_by_systemd; then
        echo "systemd: $(systemctl is-active "$UNIT"), main PID $(systemctl show -p MainPID --value "$UNIT")"
    else
        echo "scripts: $( [[ -f runtime/backend.pid ]] && echo "PID $(cat runtime/backend.pid)" || echo "not running")"
    fi
    ;;
*)
    echo "usage: $0 {start|stop|restart|status}"
    exit 2
    ;;
esac
