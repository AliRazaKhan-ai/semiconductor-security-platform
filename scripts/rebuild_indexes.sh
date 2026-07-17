#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
cd "$ROOT"
exec "$VENV/bin/flask" --app app.factory:create_app rebuild-event-store

