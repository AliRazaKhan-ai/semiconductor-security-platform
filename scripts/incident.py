"""Purpose: Open an incident record for a quarantined chip.
Directory: scripts.
Dependencies: app.storage.quarantine.
Connection: reads run records, writes data/incidents. Never touches the ledger.

    incident.py list              chips currently quarantined
    incident.py open <scan_id>    assemble and save an incident record
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.quarantine import list_quarantined, open_incident, save_incident  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "open"))
    parser.add_argument("scan_id", nargs="?")
    args = parser.parse_args()

    if args.action == "list":
        rows = list_quarantined()
        if not rows:
            print("No quarantined chips.")
            return 0
        print(f"{'chip':32} {'decision':30} scan")
        for row in rows:
            print(f"{row['chip_id']:32} {row['deployment_decision']:30} {row['scan_id']}")
        return 0

    if not args.scan_id:
        parser.error("open requires a scan_id")

    incident = open_incident(args.scan_id)
    if incident is None:
        print(f"No run found for scan {args.scan_id}")
        return 1

    path = save_incident(incident)
    print(json.dumps(incident.to_dict(), indent=2))
    print(f"\nsaved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
