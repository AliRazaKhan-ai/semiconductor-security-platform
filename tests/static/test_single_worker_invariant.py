"""Purpose: Pin the single-worker assumption the in-memory rate limiter depends on.
Directory: tests/static.
Dependencies: pytest, re, pathlib.
Connection: Guards RISK-06. app/security/rate_limiting.py holds its counters in
process memory, so the configured limits - 120 per 60s general, 20 per 60s for scan
submission - are per worker. Threads share one counter and are safe; a second worker
would silently double the effective limit. Both gunicorn.conf.py and
scripts/runtime/start_backend.sh set one worker, and this asserts they stay agreed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.security
def test_gunicorn_config_runs_a_single_worker() -> None:
    source = (ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
    match = re.search(r"^workers\s*=\s*(\d+)", source, re.M)

    assert match, "gunicorn.conf.py does not set workers"
    assert int(match.group(1)) == 1, (
        "The rate limiter keeps counters in process memory. More than one worker "
        "multiplies the effective limit by the worker count."
    )


@pytest.mark.security
def test_launch_script_runs_a_single_worker() -> None:
    source = (ROOT / "scripts" / "runtime" / "start_backend.sh").read_text(
        encoding="utf-8"
    )
    match = re.search(r"--workers\s+(\d+)", source)

    assert match, "start_backend.sh does not pass --workers"
    assert int(match.group(1)) == 1


@pytest.mark.security
def test_rate_limiting_is_still_in_process() -> None:
    """If the limiter gains a shared backend, the invariant above can be relaxed."""
    source = (ROOT / "app" / "security" / "rate_limiting.py").read_text(
        encoding="utf-8"
    )

    assert not re.search(r"\bredis\b|\bmemcache", source, re.I), (
        "The limiter appears to use a shared backend. Revisit RISK-06: the "
        "single-worker constraint may no longer be required."
    )
