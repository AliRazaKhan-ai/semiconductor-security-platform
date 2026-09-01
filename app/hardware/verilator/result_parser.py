from __future__ import annotations

import re


def _summary_int(output: str, name: str) -> int | None:
    matches = re.findall(
        rf"^\s*{re.escape(name)}\s*[:=]\s*(\d+)\s*$",
        output,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return int(matches[-1]) if matches else None


def _summary_flag(output: str, name: str) -> bool:
    return bool(
        re.search(
            rf"^\s*{re.escape(name)}\s*[:=]\s*1\s*$",
            output,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )


def parse_output(
    build_log: str,
    output: str,
) -> tuple[tuple[str, ...], int, int, tuple[str, ...]]:
    reasons: list[str] = []

    warnings = tuple(
        line.strip()
        for line in build_log.splitlines()
        if "%Warning" in line
    )

    upper_output = output.upper()

    if any(
        token in upper_output
        for token in (
            "ASSERTION FAILED",
            "%ERROR",
            "$FATAL",
            "TEST FAILED",
        )
    ):
        reasons.append("SIMULATION_ASSERTION_FAILURE")

    assertions = _summary_int(output, "ASSERTIONS")
    cycles = _summary_int(output, "CYCLES")

    if assertions is None:
        reasons.append("ASSERTION_SUMMARY_MISSING")
        assertions = 0
    elif assertions < 1:
        reasons.append("ASSERTION_COUNT_INSUFFICIENT")

    if cycles is None:
        reasons.append("CYCLE_SUMMARY_MISSING")
        cycles = 0
    elif cycles < 1:
        reasons.append("CYCLE_COUNT_INSUFFICIENT")

    if not _summary_flag(output, "RESET_COMPLETED"):
        reasons.append("RESET_COMPLETION_MISSING")

    if not _summary_flag(output, "REQUIRED_CHECKS_PASSED"):
        reasons.append("REQUIRED_CHECKS_MISSING")

    if "SEMISURE_PASS" not in output:
        reasons.append("PASS_MARKER_MISSING")

    return tuple(reasons), assertions, cycles, warnings
