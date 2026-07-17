#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
if [[ ! -x "$VENV/bin/python" ]]; then
  printf 'Virtual environment not found. Run scripts/install_dependencies.sh first.\n' >&2
  exit 1
fi
cd "$ROOT"
set -a
[[ -f .env ]] && source .env
set +a
exec "$VENV/bin/python" manage.py "$@"

