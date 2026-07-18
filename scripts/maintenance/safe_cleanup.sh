#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Disk usage before cleanup:"
df -h /

echo
echo "Cleaning Python caches..."
find "$PROJECT_ROOT" \
  -type d \
  \( \
    -name '__pycache__' \
    -o -name '.pytest_cache' \
    -o -name '.mypy_cache' \
    -o -name '.ruff_cache' \
  \) \
  -prune \
  -exec rm -rf {} +

find "$PROJECT_ROOT" \
  -type f \
  \( -name '*.pyc' -o -name '*.pyo' \) \
  -delete

echo "Cleaning pip cache..."
"$PROJECT_ROOT/venv/bin/python" -m pip cache purge || true

echo "Truncating runtime logs..."
mkdir -p runtime
: > runtime/backend.log
: > runtime/anvil.log

find runtime \
  -maxdepth 1 \
  -type f \
  \( \
    -name 'demo-*.json' \
    -o -name 'exam-*.json' \
    -o -name '*.log.*' \
  \) \
  -delete

echo "Removing patch backup files..."
find "$PROJECT_ROOT" \
  -type f \
  \( \
    -name '*.before_*' \
    -o -name '*.before-*' \
    -o -name '*.bak' \
    -o -name '*~' \
  \) \
  -delete

echo "Skipping Docker container pruning."
echo "Fabric containers may be stopped but are still required."

echo "Removing dangling Docker images..."
docker image prune -f || true

echo "Removing Docker build cache..."
docker builder prune -f || true

echo
echo "Disk usage after cleanup:"
df -h /

echo
echo "Largest project directories:"
du -xhd2 "$PROJECT_ROOT" 2>/dev/null \
  | sort -h \
  | tail -20
