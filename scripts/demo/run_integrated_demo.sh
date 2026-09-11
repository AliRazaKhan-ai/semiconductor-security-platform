#!/usr/bin/env bash
# Purpose: Mint evidence and run chips through IntegratedPipelineService, interleaved.
# Directory: scripts/demo
# Dependencies: scripts/demo/mint_hardware_evidence.py; manage.py integrated-run
#
# WHY INTERLEAVED. A PUF challenge is single-use and expires 120 seconds after issue;
# OpenTitan attestation expires after 300 seconds and its counter cannot be reused.
# Minting every chip and then running every chip leaves the first chip's evidence stale
# before its run begins. Each chip is therefore minted immediately before it runs.
#
# Roughly 60 seconds to mint a chip and 16 to run it. One chip is about 75 seconds; all
# eight about ten minutes.

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
source venv/bin/activate

CHIPS=()
if [[ $# -eq 0 ]]; then
    CHIPS=("chip_01_good.json")
elif [[ "${1:-}" == "--all" ]]; then
    while IFS= read -r path; do
        CHIPS+=("$(basename "$path")")
    done < <(find data/chips -maxdepth 1 -name "chip_*.json" | sort)
else
    CHIPS=("$@")
fi

echo "=========================================="
echo " SemiSecure integrated pipeline"
echo " Chips: ${CHIPS[*]}"
echo "=========================================="

mkdir -p runtime evidence/demo
STAMP="$(date +%Y%m%d-%H%M)"
SUMMARY="evidence/demo/integrated_demo_${STAMP}.txt"

{
    echo "=== SemiSecure integrated pipeline, $(date -Is) ==="
    echo "Each chip is minted immediately before it runs: PUF challenges are"
    echo "single-use and OpenTitan attestation expires after 300 seconds."
    echo
} > "$SUMMARY"

FAILED=0

for chip in "${CHIPS[@]}"; do
    echo
    echo "------------------------------------------"
    echo " $chip"
    echo "------------------------------------------"

    if ! python scripts/demo/mint_hardware_evidence.py --only "$chip"; then
        echo "MINT FAILED: $chip" | tee -a "$SUMMARY"
        FAILED=$((FAILED + 1))
        continue
    fi

    if ! python manage.py integrated-run "data/chips/$chip" --force \
        > "runtime/integrated-${chip%.json}.json"; then
        echo "RUN FAILED: $chip" | tee -a "$SUMMARY"
        FAILED=$((FAILED + 1))
        continue
    fi

    python - "$chip" <<'PY' | tee -a "$SUMMARY"
import json
import sys
from pathlib import Path

chip = sys.argv[1]
payload = json.loads(Path(f"runtime/integrated-{chip[:-5]}.json").read_text())
run = payload.get("run", payload)

print(
    f"{run.get('chip_id', chip):32} {str(run.get('status')):20} "
    f"decision={run.get('deployment_decision')}"
)
for stage in run.get("stages", []):
    print(f"    {stage['stage']:22} {stage['status']}")
PY
done

echo
echo "==========================================" | tee -a "$SUMMARY"
if [[ "$FAILED" -eq 0 ]]; then
    echo " All ${#CHIPS[@]} chip(s) completed" | tee -a "$SUMMARY"
else
    echo " $FAILED of ${#CHIPS[@]} chip(s) failed" | tee -a "$SUMMARY"
fi
echo " Dashboard: http://127.0.0.1:5000/dashboard" | tee -a "$SUMMARY"
echo " Evidence:  $SUMMARY" | tee -a "$SUMMARY"
echo "=========================================="

exit "$FAILED"
