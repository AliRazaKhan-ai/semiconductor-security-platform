#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
[[ -x "$VENV/bin/python" ]] || { echo 'Python virtual environment is missing.' >&2; exit 1; }
"$VENV/bin/python" --version
"$VENV/bin/python" -m pip check
cd "$ROOT"
"$VENV/bin/python" -m compileall -q app manage.py wsgi.py gunicorn.conf.py
"$VENV/bin/python" manage.py --verify-event-store
printf 'Environment verification completed successfully.\n'

