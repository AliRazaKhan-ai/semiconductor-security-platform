#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SEMISURE_LOG_DIR:-$ROOT/runtime/logs}"
RETENTION_DAYS="${SEMISURE_LOG_RETENTION_DAYS:-30}"
mkdir -p "$LOG_DIR"
find "$LOG_DIR" -type f -name '*.jsonl.*' -mtime "+$RETENTION_DAYS" -delete
find "$LOG_DIR" -type f -name '*.jsonl' -size +100M -print0 | while IFS= read -r -d '' file; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$file" "$file.$timestamp"
  gzip -9 "$file.$timestamp"
  : > "$file"
done

