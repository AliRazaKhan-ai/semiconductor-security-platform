"""Purpose: Patch build_ai_evidence to consume evidence_features derivations.

Directory: scripts/maintenance
Dependencies: standard library
Connection: one-shot patch for app/integration/adapters.py

Two of the six edits replace multi-line blocks in a one-argument-per-line style. sed range
addresses give no guarantee an anchor matched exactly once: zero matches silently no-op and
two matches corrupt the file. This script asserts exactly-once for every anchor and aborts
having written nothing if any assertion fails. Dry-run by default.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

TARGET = Path("app/integration/adapters.py")
BACKUP = Path("app/integration/adapters.py.pre-file3")

EDITS: list[tuple[str, str, str]] = [
    (
        "1 import evidence_features",
        "from app.hardware.common import HardwareIntegrationError\n",
        "from app.hardware.common import HardwareIntegrationError\n"
        "from app.integration import evidence_features\n",
    ),
    (
        "2 schema_version parameter",
        "    hardware_result: Mapping[str, Any],\n"
        ") -> dict[str, Any]:\n"
        '    """Build strict AI evidence from explicit and verified preceding evidence."""\n',
        "    hardware_result: Mapping[str, Any],\n"
        "    schema_version: str | None = None,\n"
        ") -> dict[str, Any]:\n"
        '    """Build strict AI evidence from explicit and verified preceding evidence."""\n',
    ),
    (
        "3 derive relative features, schema-aware contract",
        "    missing_model_features = [\n"
        '        "yosys.gate_count",\n'
        '        "yosys.unused_logic_ratio",\n'
        '        "yosys.rare_net_count",\n'
        '        "yosys.netlist_delta_ratio",\n'
        "    ]\n"
        "\n"
        "    if not verified_puf:\n"
        "        missing_model_features.append(\n"
        '            "puf.verified_authentication"\n'
        "        )\n",
        "    # Reference-relative design features. A hardware Trojan is characterised by\n"
        "    # divergence from a known-good reference, not by absolute design size, so these\n"
        "    # are the only design features that can express one. Absence stays absent: a\n"
        "    # feature defaulted to 0.0 would reach the model as a constant column.\n"
        "    netlist_delta = evidence_features.netlist_delta_ratio(\n"
        "        yosys\n"
        "    )\n"
        "\n"
        "    simulation_failure = evidence_features.simulation_failure_ratio(\n"
        "        verilator\n"
        "    )\n"
        "\n"
        "    active_schema = (\n"
        '        str(schema_version) if schema_version else "1.0"\n'
        "    )\n"
        "\n"
        "    missing_model_features = evidence_features.missing_model_features(\n"
        "        schema_version=active_schema,\n"
        "        netlist_delta=netlist_delta,\n"
        "        simulation_failure=simulation_failure,\n"
        "        puf_verified=verified_puf,\n"
        "    )\n",
    ),
    (
        "4 surface netlist_delta_ratio into the yosys block",
        '            "combinational_cells": (\n'
        "                combinational_cells\n"
        "            ),\n"
        "        },\n",
        '            "combinational_cells": (\n'
        "                combinational_cells\n"
        "            ),\n"
        '            "netlist_delta_ratio": (\n'
        "                netlist_delta\n"
        "            ),\n"
        "        },\n",
    ),
    (
        "5 unpin failed_assertions",
        '            "failed_assertions": 0,\n'
        "        },\n",
        '            "failed_assertions": (\n'
        "                round(\n"
        "                    simulation_failure[0]\n"
        "                    * assertion_count\n"
        "                )\n"
        "                if simulation_failure is not None\n"
        "                else 0\n"
        "            ),\n"
        '            "failed_assertions_is_lower_bound": (\n'
        "                simulation_failure is not None\n"
        "                and not simulation_failure[1]\n"
        "            ),\n"
        "        },\n",
    ),
    (
        "6 compute evidence_quality",
        '        "evidence_quality": 0.0,\n',
        '        "evidence_quality": evidence_features.evidence_quality(\n'
        "            stages=stages,\n"
        "            puf_verified=verified_puf,\n"
        "            physical_capture=bool(\n"
        "                chipwhisperer.get(\n"
        '                    "physical_capture_verified",\n'
        "                    False,\n"
        "                )\n"
        "            ),\n"
        "            structural_baseline_applied=(\n"
        "                netlist_delta is not None\n"
        "            ),\n"
        "        ),\n",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch build_ai_evidence.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the changes; without this flag the script only reports",
    )
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"FAIL: {TARGET} not found. Run from the project root.", file=sys.stderr)
        return 2

    original = TARGET.read_text(encoding="utf-8")
    patched = original
    failures: list[str] = []

    for name, anchor, replacement in EDITS:
        count = patched.count(anchor)
        if count != 1:
            failures.append(f"{name}: anchor matched {count} times, expected exactly 1")
            continue
        if replacement in patched:
            failures.append(f"{name}: replacement already present, patch may be reapplied")
            continue
        patched = patched.replace(anchor, replacement, 1)
        print(f"OK   {name}")

    if failures:
        print("\nABORTED. Nothing written.\n", file=sys.stderr)
        for failure in failures:
            print(f"  FAIL {failure}", file=sys.stderr)
        return 3

    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(TARGET),
            tofile=f"{TARGET} (patched)",
            n=2,
        )
    )

    print(f"\n--- unified diff, {len(diff)} lines ---")
    sys.stdout.writelines(diff)

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return 0

    BACKUP.write_text(original, encoding="utf-8")
    TARGET.write_text(patched, encoding="utf-8")
    print(f"\nWROTE {TARGET}")
    print(f"BACKUP {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
