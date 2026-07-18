#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

source venv/bin/activate

echo "=========================================="
echo " SemiSecure Examination Demonstration"
echo "=========================================="

./scripts/runtime/start_everything.sh

echo
echo "[1] Running all five security scenarios"

python manage.py pipeline-all \
  data/chips \
  --force \
  | tee runtime/exam-pipeline-results.json

echo
echo "[2] Verifying event-store integrity"

python manage.py verify-event-store \
  | tee runtime/exam-event-store-verification.json

echo
echo "[3] Checking blockchain services"

curl -fsS \
  http://127.0.0.1:5000/api/v1/blockchain/status \
  | python -m json.tool \
  | tee runtime/exam-blockchain-status.json

echo
echo "[4] Checking dashboard"

ROOT_STATUS="$(
  curl -sS -o /dev/null -w '%{http_code}' \
  http://127.0.0.1:5000/
)"

DASHBOARD_STATUS="$(
  curl -sS -o /dev/null -w '%{http_code}' \
  http://127.0.0.1:5000/dashboard
)"

test "$ROOT_STATUS" = "200"
test "$DASHBOARD_STATUS" = "200"

echo "Dashboard root: HTTP $ROOT_STATUS"
echo "Dashboard page: HTTP $DASHBOARD_STATUS"

echo
echo "[5] Strict laboratory-evidence status"

if python scripts/integration/check_hardware_manifests.py \
  | tee runtime/exam-hardware-manifest-status.json
then
  echo "Strict physical integration: READY"
else
  echo "Strict physical integration: WAITING FOR LABORATORY EVIDENCE"
fi

echo
echo "=========================================="
echo " Demonstration completed"
echo " Dashboard: http://127.0.0.1:5000/dashboard"
echo "=========================================="
