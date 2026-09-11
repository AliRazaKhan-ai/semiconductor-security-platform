"""Purpose: Mint and run chips through IntegratedPipelineService in one process.

Directory: scripts/demo
Dependencies: scripts/demo/mint_hardware_evidence.py; app.create_app
Connection: replaces the per-chip subprocess loop in run_integrated_demo.sh

WHY ONE PROCESS. The shell loop invoked manage.py once per chip, so TensorFlow was
imported and the models reloaded for every chip: about 40 seconds each, against 34
seconds of actual analysis. Here the application is created once and reused.

WHY STILL INTERLEAVED. A PUF challenge is single-use and OpenTitan attestation expires
300 seconds after minting, so each chip is minted immediately before it runs. Minting
all chips first would leave the earliest stale before its run began.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

MINT_SCRIPT = PROJECT_ROOT / "scripts" / "demo" / "mint_hardware_evidence.py"
CHIPS_DIR = PROJECT_ROOT / "data" / "chips"


def mint(chip: str, quiet: bool) -> bool:
    argv, stdout = sys.argv, sys.stdout
    sys.argv = [MINT_SCRIPT.name, "--only", chip]
    if quiet:
        sys.stdout = open("/dev/null", "w")  # noqa: SIM115
    try:
        runpy.run_path(str(MINT_SCRIPT), run_name="__main__")
        return True
    except SystemExit as exit_code:
        return exit_code.code in (0, None)
    except Exception as error:  # noqa: BLE001 - report and continue to the next chip
        sys.stdout = stdout
        print(f"    MINT FAILED: {type(error).__name__}: {error}", flush=True)
        return False
    finally:
        if quiet and sys.stdout is not stdout:
            sys.stdout.close()
        sys.argv, sys.stdout = argv, stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mint and run chips through the integrated pipeline."
    )
    parser.add_argument("chips", nargs="*", help="fixture filenames")
    parser.add_argument("--all", action="store_true", help="every chip fixture")
    parser.add_argument("--quiet-mint", action="store_true", help="suppress mint output")
    args = parser.parse_args()

    if args.all:
        chips = [path.name for path in sorted(CHIPS_DIR.glob("chip_*.json"))]
    elif args.chips:
        chips = list(args.chips)
    else:
        chips = ["chip_01_good.json"]

    print("=" * 66)
    print(" SemiSecure integrated pipeline")
    print(f" Chips: {len(chips)}")
    print("=" * 66, flush=True)

    started = time.perf_counter()
    print("\nLoading models (paid once for the whole run) ...", flush=True)

    from app import create_app

    service = create_app().extensions["semisecure.integrated_pipeline"]
    print(f"  ready in {time.perf_counter() - started:.1f}s", flush=True)

    results: list[tuple[str, str, str, float]] = []
    failed = 0

    for index, chip in enumerate(chips, start=1):
        print(f"\n[{index}/{len(chips)}] {chip}", flush=True)
        chip_started = time.perf_counter()

        if not mint(chip, args.quiet_mint):
            failed += 1
            results.append((chip, "MINT_FAILED", "-", time.perf_counter() - chip_started))
            continue

        try:
            run = service.run_file(CHIPS_DIR / chip, force=True)["run"]
        except Exception as error:  # noqa: BLE001 - one chip must not end the run
            failed += 1
            print(f"    RUN FAILED: {type(error).__name__}: {error}", flush=True)
            results.append((chip, "RUN_FAILED", "-", time.perf_counter() - chip_started))
            continue

        elapsed = time.perf_counter() - chip_started
        status = str(run.get("status"))
        decision = str(run.get("deployment_decision"))
        results.append((chip, status, decision, elapsed))

        print(f"    {status}  {decision}  ({elapsed:.1f}s)", flush=True)
        for stage in run.get("stages", []):
            print(f"      {stage['stage']:22} {stage['status']}")

    total = time.perf_counter() - started

    print("\n" + "=" * 66)
    print(f" {'chip':32} {'status':22} {'s':>6}")
    print("-" * 66)
    for chip, status, decision, elapsed in results:
        print(f" {chip:32} {status:22} {elapsed:6.1f}")
        print(f" {'':32} {decision}")
    print("-" * 66)
    print(f" {len(chips)} chip(s) in {total:.1f}s, {total / max(1, len(chips)):.1f}s each")
    print(f" {failed} failure(s)")
    print(" Dashboard: http://127.0.0.1:5000/dashboard")
    print("=" * 66)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
