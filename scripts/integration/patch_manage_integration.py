"""Add integrated terminal commands to manage.py."""

from pathlib import Path


path = Path("manage.py")
text = path.read_text(
    encoding="utf-8"
)

import_line = (
    "from app.integration import "
    "IntegratedPipelineService\n"
)

if import_line not in text:
    anchor = (
        "from app.factory import create_app\n"
    )

    if anchor not in text:
        raise SystemExit(
            "create_app import was not found"
        )

    text = text.replace(
        anchor,
        anchor + import_line,
        1,
    )

functions = '''

def integrated_service() -> IntegratedPipelineService:
    """Build the complete terminal-to-dashboard integration."""
    application = create_app()

    service = application.extensions.get(
        "semisecure.integrated_pipeline"
    )

    if not isinstance(
        service,
        IntegratedPipelineService,
    ):
        raise CommandFailure(
            "Integrated pipeline is unavailable"
        )

    return service


def command_integrated_run(
    args: argparse.Namespace,
) -> int:
    """Run every module for one chip."""
    result = integrated_service().run_file(
        Path(args.file),
        force=args.force,
    )

    print_json(result)
    return 0


def command_integrated_all(
    args: argparse.Namespace,
) -> int:
    """Run every module for every chip JSON file."""
    directory = Path(
        args.directory
    ).expanduser().resolve()

    if not directory.is_dir():
        raise CommandFailure(
            f"Directory does not exist: {directory}"
        )

    results = []
    failures = []

    for file_path in sorted(
        directory.glob("*.json")
    ):
        try:
            result = integrated_service().run_file(
                file_path,
                force=args.force,
            )

            run = result["run"]

            results.append(
                {
                    "file": file_path.name,
                    "run_id": run["run_id"],
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
                    "file": file_path.name,
                    "error_type": (
                        type(exc).__name__
                    ),
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


def command_integrated_status(
    args: argparse.Namespace,
) -> int:
    """Display one integrated run."""
    run = integrated_service().get_run(
        args.identifier
    )

    print_json(run)
    return 0

'''

if "def command_integrated_run(" not in text:
    marker = "\ndef add_server_arguments("

    if marker not in text:
        raise SystemExit(
            "add_server_arguments was not found"
        )

    text = text.replace(
        marker,
        functions + marker,
        1,
    )

parser_block = '''
    integrated_run_parser = commands.add_parser(
        "integrated-run",
        help=(
            "Run terminal, PUF, hardware, AI, compliance, "
            "blockchain, dashboard, and deployment."
        ),
    )
    integrated_run_parser.add_argument("file")
    integrated_run_parser.add_argument(
        "--force",
        action="store_true",
    )

    integrated_all_parser = commands.add_parser(
        "integrated-all",
        help="Run complete integration for every chip JSON file.",
    )
    integrated_all_parser.add_argument("directory")
    integrated_all_parser.add_argument(
        "--force",
        action="store_true",
    )
    integrated_all_parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )

    integrated_status_parser = commands.add_parser(
        "integrated-status",
        help="Show a complete integrated pipeline run.",
    )
    integrated_status_parser.add_argument(
        "identifier"
    )

'''

if '"integrated-run"' not in text:
    marker = "    return parser\n"

    if marker not in text:
        raise SystemExit(
            "Parser return statement was not found"
        )

    text = text.replace(
        marker,
        parser_block + marker,
        1,
    )

handlers = '''        "integrated-run": command_integrated_run,
        "integrated-all": command_integrated_all,
        "integrated-status": command_integrated_status,
'''

if (
    '"integrated-run": command_integrated_run'
    not in text
):
    marker = (
        '        "pipeline-run": '
        "command_pipeline_run,\n"
    )

    if marker not in text:
        marker = (
            '        "scan": command_scan,\n'
        )

    if marker not in text:
        raise SystemExit(
            "Command handler insertion point was not found"
        )

    text = text.replace(
        marker,
        marker + handlers,
        1,
    )

path.write_text(
    text,
    encoding="utf-8",
)

print("Integrated terminal commands installed")
