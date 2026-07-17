#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${SEMISURE_DATA_DIR:-$ROOT/data}"
RUNTIME_ROOT="${SEMISURE_RUNTIME_DIR:-$ROOT/runtime}"
mkdir -p \
  "$DATA_ROOT/event_store" \
  "$DATA_ROOT/indexes" \
  "$DATA_ROOT/snapshots/scans" \
  "$DATA_ROOT/audit" \
  "$RUNTIME_ROOT/logs" \
  "$RUNTIME_ROOT/locks/scans" \
  "$RUNTIME_ROOT/locks/indexes" \
  "$RUNTIME_ROOT/locks/snapshots" \
  "$RUNTIME_ROOT/locks/audit"
chmod 750 "$DATA_ROOT" "$RUNTIME_ROOT"
find "$DATA_ROOT" "$RUNTIME_ROOT" -type d -exec chmod 750 {} +
printf 'JSON event-store directories initialised.\n'

