"""Purpose: Verify the Phase 3 terminal command interface.
Directory: tests/unit.
Dependencies: manage.build_parser.
Connection: Prevents removal of required terminal commands.
"""

from manage import build_parser


def test_scan_command_is_registered() -> None:
    args = build_parser().parse_args(
        ["scan", "data/chips/chip_01_good.json"]
    )

    assert args.command == "scan"
    assert args.file.endswith("chip_01_good.json")


def test_scan_all_command_is_registered() -> None:
    args = build_parser().parse_args(
        ["scan-all", "data/chips"]
    )

    assert args.command == "scan-all"


def test_verify_scan_command_is_registered() -> None:
    args = build_parser().parse_args(
        ["verify-scan", "scan-123"]
    )

    assert args.command == "verify-scan"
    assert args.scan_id == "scan-123"


def test_operational_commands_are_registered() -> None:
    assert (
        build_parser().parse_args(
            ["verify-event-store"]
        ).command
        == "verify-event-store"
    )

    assert (
        build_parser().parse_args(
            ["system-status"]
        ).command
        == "system-status"
    )

    assert (
        build_parser().parse_args(
            ["export-audit", "scan-123"]
        ).command
        == "export-audit"
    )
