#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$ROOT/scripts/create_virtualenv.sh" "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -e "$ROOT[dev]"
"$VENV/bin/python" -m pip check

