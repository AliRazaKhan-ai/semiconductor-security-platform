#!/usr/bin/env python3
"""EDA toolchain integrity check.

Yosys and Verilator produce the evidence this platform's Trojan verdicts rest
on. A substituted Yosys that reports eight cells for a twenty-seven cell
netlist would defeat every downstream control silently, and nothing else in
the pipeline would notice.

So the toolchain is enrolled, not trusted. Each environment that is allowed to
produce evidence is recorded in the manifest with its version string and the
SHA-256 of the binary. Three outcomes:

  known      version and digest both match an enrolled environment  -> pass
  TAMPERED   version matches but the digest does not                -> fail
  unknown    version not enrolled at all                            -> fail

An unknown toolchain fails rather than warns. Enrolling one is a deliberate
commit a reviewer can see, which is the entire point: the control is the
requirement to decide, not the file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evidence/devsecops/eda_toolchain_manifest.json"
TOOLS = (("yosys", ["yosys", "-V"]), ("verilator", ["verilator", "--version"]))


def resolve(tool: str) -> Path:
    found = shutil.which(tool)
    if not found:
        raise SystemExit(f"{tool} is not on PATH")
    # Follow symlinks: /usr/bin/yosys may point at a versioned binary, and the
    # digest of the link tells us nothing about what actually runs.
    return Path(os.path.realpath(found))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def version(argv: list[str]) -> str:
    done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    text = (done.stdout or done.stderr).strip()
    return text.splitlines()[0] if text else "unknown"


def observe() -> dict:
    current: dict = {}
    for tool, argv in TOOLS:
        path = resolve(tool)
        current[tool] = {
            "version": version(argv),
            "sha256": digest(path),
            "path": str(path),
        }
    return current


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        return {"environments": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        metavar="NAME",
        help="enrol the current toolchain under this environment name",
    )
    args = parser.parse_args()

    current = observe()
    manifest = load_manifest()

    print("=" * 72)
    print("EDA TOOLCHAIN INTEGRITY")
    print("=" * 72)
    for tool in current:
        print(f"  {tool:<10} {current[tool]['version']}")
        print(f"  {'':<10} sha256 {current[tool]['sha256']}")
        print(f"  {'':<10} path   {current[tool]['path']}")
    print()

    if args.update:
        entry = {"name": args.update}
        for tool in current:
            entry[f"{tool}_version"] = current[tool]["version"]
            entry[f"{tool}_sha256"] = current[tool]["sha256"]
        # Replace an existing entry of the same name rather than accumulating
        # duplicates, so a rebuilt runner updates in place.
        others = [e for e in manifest["environments"] if e.get("name") != args.update]
        manifest["environments"] = sorted(others + [entry], key=lambda e: e["name"])
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Enrolled '{args.update}' in {MANIFEST.relative_to(ROOT)}")
        print(f"Environments now enrolled: {len(manifest['environments'])}")
        return 0

    if not manifest["environments"]:
        print("FAIL — no environments enrolled.")
        print("Enrol this one deliberately:")
        print("  python scripts/ci/eda_toolchain_check.py --update <name>")
        return 1

    tampered: list[str] = []
    for env in manifest["environments"]:
        matches_version = all(
            env.get(f"{tool}_version") == current[tool]["version"] for tool in current
        )
        if not matches_version:
            continue
        matches_digest = all(
            env.get(f"{tool}_sha256") == current[tool]["sha256"] for tool in current
        )
        if matches_digest:
            print(f"PASS — toolchain matches enrolled environment '{env['name']}'")
            return 0
        tampered.append(env["name"])

    if tampered:
        print("FAIL — TAMPERED")
        print(
            f"  Version matches enrolled environment(s) {', '.join(tampered)}, "
            "but the binary digest does not."
        )
        print("  A binary that reports the expected version with different contents")
        print("  is the exact substitution this check exists to catch.")
        print("  Do not enrol it. Reinstall the toolchain from a trusted source.")
        return 1

    print("FAIL — toolchain not enrolled")
    print("  Enrolled environments:")
    for env in manifest["environments"]:
        print(f"    {env['name']}: {env.get('yosys_version')}")
    print()
    print("  If this environment is legitimate, enrol it deliberately:")
    print("    python scripts/ci/eda_toolchain_check.py --update <name>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
