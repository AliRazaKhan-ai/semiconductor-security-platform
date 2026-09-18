#!/usr/bin/env bash
# Purpose: Archive the recoverable stores, and verify a restore into a scratch directory.
# Directory: scripts/maintenance
# Dependencies: tar, manage.py verify-event-store
#
# RISK-08. Ten snapshots existed in backups/ and no restore had ever been exercised.
# An archive nobody has restored is not a control. "verify" restores the newest
# archive into a temporary directory and runs the hash-chain check against it, so the
# archive is proven readable and internally consistent without touching live data.
#
#   backup_restore.sh backup    archive the stores
#   backup_restore.sh verify    restore the newest archive to a scratch dir and check it
#   backup_restore.sh list      show archives

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="backups"
# Recoverable state only. data/puf and data/hardware hold owner-only secret material
# and are excluded from version control and from these archives by the same reasoning.
STORES=(data/event_store data/audit data/indexes data/snapshots
        data/integrated_runs data/quarantine data/compliance)

case "${1:-}" in
backup)
    mkdir -p "$BACKUP_DIR"
    ARCHIVE="$BACKUP_DIR/stores_$(date +%Y%m%d-%H%M%S).tar.gz"
    EXISTING=()
    for store in "${STORES[@]}"; do
        [[ -d "$store" ]] && EXISTING+=("$store")
    done
    [[ ${#EXISTING[@]} -eq 0 ]] && { echo "No stores to archive."; exit 1; }
    tar czf "$ARCHIVE" "${EXISTING[@]}"
    echo "archive : $ARCHIVE"
    echo "size    : $(du -h "$ARCHIVE" | cut -f1)"
    echo "sha256  : $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
    echo
    echo "Verify it now:  $0 verify"
    ;;

verify)
    ARCHIVE="$(ls -t "$BACKUP_DIR"/stores_*.tar.gz 2>/dev/null | head -1 || true)"
    [[ -z "$ARCHIVE" ]] && { echo "No archive found. Run: $0 backup"; exit 1; }

    SCRATCH="$(mktemp -d)"
    trap 'rm -rf "$SCRATCH"' EXIT

    echo "archive : $ARCHIVE"
    echo "restore : $SCRATCH"
    tar xzf "$ARCHIVE" -C "$SCRATCH"

    FILES="$(find "$SCRATCH" -type f | wc -l)"
    echo "files   : $FILES"
    [[ "$FILES" -eq 0 ]] && { echo "RESTORE FAILED: archive is empty"; exit 1; }

    echo
    echo "--- hash chain, against the restored copy ---"
    SEMISURE_DATA_DIR="$SCRATCH/data" \
        ./venv/bin/python manage.py verify-event-store
    echo
    echo "RESTORE VERIFIED. Live data untouched."
    ;;

list)
    ls -lht "$BACKUP_DIR"/stores_*.tar.gz 2>/dev/null || echo "No archives."
    ;;

*)
    echo "usage: $0 {backup|verify|list}"
    exit 2
    ;;
esac
