#!/usr/bin/env python3
"""Blocking RTL security gate for CI.

Continuous security testing for the reference design. Three properties are
checked on every commit:

  1. The reference RTL still matches a digest pinned in reviewed configuration.
     YosysAdapter enforces this itself; a reference an attacker can edit is not
     a baseline, because a Trojan inserted into both sides differences to zero.

  2. The reference differenced against itself yields a zero delta. If this ever
     fails, the synthesis path is non-deterministic and every Trojan verdict the
     platform has produced is worthless.

  3. The controlled Trojan differenced against the reference is still FLAGGED.
     A reference-only check passes even if the detector has been broken to
     report a constant. Checking both sides is what makes this a gate.

Absolute cell counts are compared only when the toolchain matches the recorded
baseline. Yosys versions differ between a developer machine and a hosted
runner, and a gate that fails on a toolchain difference rather than a security
finding gets switched off.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.hardware.verilator.runner import VerilatorRunner  # noqa: E402
from app.hardware.yosys import YosysAdapter  # noqa: E402

REFERENCE_RTL = ROOT / "hardware_lab/rtl/reference/semisecure_demo_core.sv"
TROJAN_RTL = ROOT / "hardware_lab/rtl/controlled_trojan/semisecure_demo_core_trojan.sv"
TESTBENCH = ROOT / "hardware_lab/verilator/testbenches/tb_semisecure_demo_core.sv"
BASELINE = ROOT / "evidence/devsecops/rtl_gate_baseline.json"
TOP = "semisecure_demo_core"

MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)


def first_module(path: Path) -> str:
    match = MODULE_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"no module declaration found in {path}")
    return match.group(1)


def tool_version(argv: list[str]) -> str:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable ({exc})"
    text = (done.stdout or done.stderr).strip()
    return text.splitlines()[0] if text else "unknown"


class Gate:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.lines: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        self.lines.append(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.failures.append(label)

    def note(self, text: str) -> None:
        self.lines.append(f"         {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="record the current metrics as the baseline instead of asserting against it",
    )
    args = parser.parse_args()

    for path in (REFERENCE_RTL, TROJAN_RTL, TESTBENCH):
        if not path.is_file():
            raise SystemExit(f"missing required file: {path}")

    yosys_version = tool_version(["yosys", "-V"])
    verilator_version = tool_version(["verilator", "--version"])

    gate = Gate()
    print("=" * 72)
    print("RTL SECURITY GATE")
    print("=" * 72)
    print(f"  yosys      : {yosys_version}")
    print(f"  verilator  : {verilator_version}")
    print(f"  top module : {TOP}")
    print()

    adapter = YosysAdapter.from_project(ROOT)

    # 1. Trusted reference digest. analyse_against_reference raises if the
    #    reference does not match a digest pinned in configs/hardware/yosys.json,
    #    so reaching the next line is itself the evidence.
    try:
        self_result, self_report = adapter.analyse_against_reference(
            REFERENCE_RTL, REFERENCE_RTL, TOP
        )
    except Exception as exc:  # noqa: BLE001 - the message is the finding
        gate.check(False, "reference RTL matches a trusted digest", str(exc))
        print("\n".join(gate.lines))
        print("\nGATE FAILED")
        return 1
    gate.check(True, "reference RTL matches a trusted digest")

    # 2. Determinism: the reference differenced against itself must be zero.
    self_delta = int(self_report["delta"]["absolute_cell_delta"])
    self_ratio = float(self_report["netlist_delta_ratio"])
    reference_cells = int(self_report["reference_metrics"]["cells"])
    gate.check(
        self_delta == 0 and self_ratio == 0.0,
        "reference differences to zero against itself",
        f"cell delta {self_delta}, ratio {self_ratio}",
    )
    gate.check(
        bool(self_report["structural_passed"]),
        "reference passes its own structural policy",
    )
    gate.note(f"reference cells: {reference_cells}")

    # 3. Detection: the controlled Trojan must still be flagged.
    trojan_result, trojan_report = adapter.analyse_against_reference(
        TROJAN_RTL, REFERENCE_RTL, TOP
    )
    trojan_cells = int(trojan_report["candidate_metrics"]["cells"])
    trojan_delta = int(trojan_report["delta"]["absolute_cell_delta"])
    gate.check(
        trojan_cells > reference_cells,
        "controlled Trojan synthesises to more cells than the reference",
        f"{trojan_cells} vs {reference_cells}",
    )
    gate.check(
        trojan_delta > 0,
        "structural delta is non-zero for the Trojan",
        f"cell delta {trojan_delta}",
    )
    gate.check(
        not trojan_report["structural_passed"],
        "controlled Trojan is FLAGGED by the structural policy",
        "; ".join(trojan_report["structural_reasons"]) or "no reasons recorded",
    )

    # 4. Verilator assertions on the reference. The runner raises when the build
    #    or the simulation fails, so no separate assertion parsing is needed here.
    testbench_top = first_module(TESTBENCH)
    try:
        VerilatorRunner().execute(REFERENCE_RTL, TESTBENCH, testbench_top)
        gate.check(True, "Verilator assertions pass on the reference design")
    except Exception as exc:  # noqa: BLE001 - the message is the finding
        gate.check(False, "Verilator assertions pass on the reference design", str(exc))

    observed = {
        "yosys_version": yosys_version,
        "verilator_version": verilator_version,
        "top_module": TOP,
        "reference_cells": reference_cells,
        "trojan_cells": trojan_cells,
        "trojan_cell_delta": trojan_delta,
        "reference_rtl_digest": self_report["reference_rtl_digest"],
    }

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("\n".join(gate.lines))
        print(f"\nBaseline written to {BASELINE.relative_to(ROOT)}")
        print(json.dumps(observed, indent=2, sort_keys=True))
        return 0 if not gate.failures else 1

    # 5. Exact counts, only when the toolchain matches the baseline.
    if BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        same_toolchain = baseline.get("yosys_version") == yosys_version
        if same_toolchain:
            gate.check(
                reference_cells == baseline["reference_cells"],
                "reference cell count matches baseline",
                f"{reference_cells} vs {baseline['reference_cells']}",
            )
            gate.check(
                trojan_cells == baseline["trojan_cells"],
                "Trojan cell count matches baseline",
                f"{trojan_cells} vs {baseline['trojan_cells']}",
            )
        else:
            gate.note(
                "toolchain differs from baseline; exact cell counts not asserted"
            )
            gate.note(f"baseline yosys: {baseline.get('yosys_version')}")
        gate.check(
            self_report["reference_rtl_digest"] == baseline.get("reference_rtl_digest"),
            "reference RTL digest matches baseline",
        )
    else:
        gate.note(f"no baseline at {BASELINE.relative_to(ROOT)}; run --update-baseline")

    print("\n".join(gate.lines))
    print()
    print(json.dumps(observed, indent=2, sort_keys=True))
    print()
    if gate.failures:
        print(f"GATE FAILED — {len(gate.failures)} check(s): " + "; ".join(gate.failures))
        return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
