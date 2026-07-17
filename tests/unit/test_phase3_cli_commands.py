from manage import build_parser


def test_phase3_commands_are_registered() -> None:
    assert (
        build_parser().parse_args(
            [
                "pipeline-run",
                "data/chips/chip_01_good.json",
            ]
        ).command
        == "pipeline-run"
    )

    assert (
        build_parser().parse_args(
            ["pipeline-all", "data/chips"]
        ).command
        == "pipeline-all"
    )

    assert (
        build_parser().parse_args(
            [
                "pipeline-status",
                "scan-test-12345678",
            ]
        ).command
        == "pipeline-status"
    )

    assert (
        build_parser().parse_args(
            [
                "resume-scan",
                "scan-test-12345678",
            ]
        ).command
        == "resume-scan"
    )

    assert (
        build_parser().parse_args(
            ["quarantine-list"]
        ).command
        == "quarantine-list"
    )
