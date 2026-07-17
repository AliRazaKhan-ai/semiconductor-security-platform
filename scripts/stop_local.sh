#!/usr/bin/env bash
set -euo pipefail
PIDS="$(pgrep -f '[p]ython.*manage.py|[g]unicorn.*wsgi:app' || true)"
if [[ -z "$PIDS" ]]; then
  printf 'No SemiSecure backend process is running.\n'
  exit 0
fi
kill $PIDS
for _ in {1..20}; do
  sleep 0.5
  REMAINING="$(pgrep -f '[p]ython.*manage.py|[g]unicorn.*wsgi:app' || true)"
  [[ -z "$REMAINING" ]] && exit 0
done
kill -9 $PIDS 2>/dev/null || true

