#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

source venv/bin/activate

RESULT_ROOT="$PROJECT_ROOT/runtime/test-results"
mkdir -p "$RESULT_ROOT"

echo "=============================================="
echo " SemiSecure Complete Test Suite"
echo "=============================================="

echo "[1/10] Compiling Python files"

find app tests scripts \
  -type f \
  -name '*.py' \
  -print0 \
  | xargs -0 python -m py_compile

python -m py_compile \
  manage.py \
  run.py \
  wsgi.py

echo "[2/10] Unit tests"
python -m pytest tests/unit -q \
  | tee "$RESULT_ROOT/unit.txt"

echo "[3/10] API tests"
python -m pytest tests/api -q \
  | tee "$RESULT_ROOT/api.txt"

echo "[4/10] Pipeline tests"
python -m pytest tests/pipeline -q \
  | tee "$RESULT_ROOT/pipeline.txt"

echo "[5/10] Dashboard tests"
python -m pytest tests/dashboard tests/static -q \
  | tee "$RESULT_ROOT/dashboard.txt"

echo "[6/10] AI tests"
python -m pytest tests/ai -q \
  | tee "$RESULT_ROOT/ai.txt"

echo "[7/10] Blockchain tests"
python -m pytest tests/blockchain -q \
  | tee "$RESULT_ROOT/blockchain.txt"

echo "[8/10] Security tests"
python -m pytest tests/security -q \
  | tee "$RESULT_ROOT/security.txt"

echo "[9/10] Performance tests"
python -m pytest tests/performance -q -m performance \
  | tee "$RESULT_ROOT/performance.txt"

echo "[10/10] Entire regression suite"
python -m pytest -q \
  | tee "$RESULT_ROOT/complete.txt"

echo
echo "Verifying event-store integrity"

python manage.py verify-event-store \
  | tee "$RESULT_ROOT/event-store.json"

echo
echo "=============================================="
echo " Complete test suite passed"
echo " Results: $RESULT_ROOT"
echo "=============================================="
