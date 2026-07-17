"""Idempotently add Phase 3 commands to manage.py."""

from pathlib import Path


path = Path("manage.py")
text = path.read_text(encoding="utf-8")

import_line = (
    "from app.pipeline.orchestrator import "
    "Phase3Orchestrator\n"
)

if import_line not in text:
    anchor = (
        "from app.pipeline.simulation_gate "
        "import evaluate_simulation_gate\n"
    )

    if anchor not in text:
        raise SystemExit(
            "simulation_gate import was not found"
        )

    text = text.replace(
        anchor,
        anchor + import_line,
        1,
    )

functions = r'''

def phase3_orchestrator() -> Phase3Orchestrator:
    """Construct the persistent Phase 3 orchestrator."""
    return Phase3Orchestrator(PROJECT_ROOT)


def command_pipeline_run(args: argparse.Namespace) -> int:
    """Run one complete persistent Phase 3 pipeline."""
    result = phase3_orchestrator().run(
        Path(args.file),
        force=args.force,
    )
    print_json(result)
    return 0


def command_pipeline_all(args: argparse.Namespace) -> int:
    """Run all chip simulations through Phase 3."""
    directory = Path(args.directory).expanduser().resolve()

    if not directory.is_dir():
        raise CommandFailure(
            f"Directory does not exist: {directory}"
        )

    results = []
    failures = []

    for path in sorted(directory.glob("*.json")):
        try:
            result = phase3_orchestrator().run(
                path,
                force=args.force,
            )
            run = result["run"]

            results.append(
                {
                    "file": path.name,
                    "scan_id": run["scan_id"],
                    "scenario": run["scenario"],
                    "status": run["status"],
                    "stopped_stage": run[
                        "stopped_stage"
                    ],
                    "deployment_decision": run[
                        "deployment_decision"
                    ],
                    "quarantined": run[
                        "quarantined"
                    ],
                    "idempotent_replay": result[
                        "idempotent_replay"
                    ],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "file": path.name,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

            if args.stop_on_error:
                break

    print_json(
        {
            "processed": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }
    )

    return 1 if failures else 0


def command_pipeline_status(
    args: argparse.Namespace,
) -> int:
    """Show a persistent Phase 3 pipeline run."""
    scan_id = validate_scan_id(args.scan_id)
    print_json(
        phase3_orchestrator().status(scan_id)
    )
    return 0


def command_resume_scan(args: argparse.Namespace) -> int:
    """Resume an incomplete pipeline as a new run."""
    scan_id = validate_scan_id(args.scan_id)
    print_json(
        phase3_orchestrator().resume(scan_id)
    )
    return 0


def command_quarantine_list(
    args: argparse.Namespace,
) -> int:
    """List fail-closed and denied chips."""
    records = phase3_orchestrator().quarantine_list()

    print_json(
        {
            "count": len(records),
            "records": records,
        }
    )
    return 0

'''

if "def command_pipeline_run(" not in text:
    marker = "\ndef add_server_arguments("

    if marker not in text:
        raise SystemExit(
            "add_server_arguments marker not found"
        )

    text = text.replace(
        marker,
        functions + marker,
        1,
    )

parser_block = r'''
    pipeline_run_parser = commands.add_parser(
        "pipeline-run",
        help="Run one persistent fail-closed Phase 3 pipeline.",
    )
    pipeline_run_parser.add_argument("file")
    pipeline_run_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore idempotency and create a new run.",
    )

    pipeline_all_parser = commands.add_parser(
        "pipeline-all",
        help="Run every chip simulation through Phase 3.",
    )
    pipeline_all_parser.add_argument("directory")
    pipeline_all_parser.add_argument(
        "--force",
        action="store_true",
    )
    pipeline_all_parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )

    pipeline_status_parser = commands.add_parser(
        "pipeline-status",
        help="Show a persistent pipeline run.",
    )
    pipeline_status_parser.add_argument("scan_id")

    resume_parser = commands.add_parser(
        "resume-scan",
        help="Resume an incomplete pipeline as a new run.",
    )
    resume_parser.add_argument("scan_id")

    commands.add_parser(
        "quarantine-list",
        help="List quarantined and denied chips.",
    )

'''

if '"pipeline-run"' not in text:
    marker = "    return parser\n"

    if marker not in text:
        raise SystemExit(
            "build_parser return marker not found"
        )

    text = text.replace(
        marker,
        parser_block + marker,
        1,
    )

handler_entries = '''        "pipeline-run": command_pipeline_run,
        "pipeline-all": command_pipeline_all,
        "pipeline-status": command_pipeline_status,
        "resume-scan": command_resume_scan,
        "quarantine-list": command_quarantine_list,
'''

if '"pipeline-run": command_pipeline_run' not in text:
    marker = '        "scan": command_scan,\n'

    if marker not in text:
        raise SystemExit(
            "handler dictionary marker not found"
        )

    text = text.replace(
        marker,
        marker + handler_entries,
        1,
    )

path.write_text(text, encoding="utf-8")
print("Phase 3 CLI commands installed")
