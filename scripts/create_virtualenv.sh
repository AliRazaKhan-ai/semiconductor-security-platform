#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${1:-$ROOT/.venv}"
python3.12 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
printf 'Virtual environment created: %s\n' "$VENV"

