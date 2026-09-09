"""Guard against scripts that generate or overwrite live application source.

Purpose: fail the suite if any operational script writes into app/, terminal/,
manage.py, run.py or wsgi.py.
Directory: tests/static.
Dependencies: pytest, re, pathlib.
Connection: static analysis only; imports no project module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PROTECTED_DIRS = ("app", "terminal")
PROTECTED_FILES = ("manage.py", "run.py", "wsgi.py")

_PROTECTED_PATH = (
    r"(?:\./)?(?:"
    + "|".join(f"{d}/[A-Za-z0-9_./-]*" for d in PROTECTED_DIRS)
    + "|"
    + "|".join(re.escape(f) for f in PROTECTED_FILES)
    + ")"
)

SHELL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("redirect-into-source", re.compile(r">>?\s*['\"]?" + _PROTECTED_PATH)),
    ("tee-into-source", re.compile(r"\btee\b[^\n]*?['\"]?" + _PROTECTED_PATH)),
    ("sed-in-place-on-source", re.compile(r"\bsed\b[^\n]*?\s-i\b[^\n]*?" + _PROTECTED_PATH)),
    ("copy-or-move-onto-source", re.compile(r"\b(?:cp|mv|install|rsync)\b[^\n]*?\s" + _PROTECTED_PATH + r"\s*$")),
)

PYTHON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("open-source-for-write", re.compile(r"open\(\s*['\"]" + _PROTECTED_PATH + r"['\"]\s*,\s*['\"][wax]")),
    ("path-write-on-source", re.compile(r"Path\(\s*['\"]" + _PROTECTED_PATH + r"['\"]\s*\)\s*\.\s*write_")),
    ("shutil-onto-source", re.compile(r"shutil\.(?:copy\w*|move)\([^\n]*['\"]" + _PROTECTED_PATH + r"['\"]")),
)

# name = <expression containing a protected path literal>
_ASSIGN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^\n]*['\"]" + _PROTECTED_PATH + r"['\"]"
)

SCAN_DIRECTORIES = ("scripts", "dashboard_error_1_fix", "notification_fix")
SCAN_SUFFIXES = (".sh", ".py")
EXCLUDED_PARTS = ("archive", "venv", ".git", "__pycache__", "backups", "node_modules")


def _candidate_files() -> list[Path]:
    candidates: list[Path] = []

    for directory in SCAN_DIRECTORIES:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                candidates.append(path)

    candidates.extend(path for path in ROOT.glob("*.sh") if path.is_file())

    return sorted(
        path
        for path in candidates
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    )


def _scan(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:  # unreadable file is itself worth reporting
        return [f"{path.relative_to(ROOT)}: unreadable ({error})"]

    patterns = PYTHON_PATTERNS if path.suffix == ".py" else SHELL_PATTERNS
    findings: list[str] = []
    tainted: set[str] = set()

    for number, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0] if path.suffix == ".py" else raw
        if not line.strip():
            continue

        for label, pattern in patterns:
            if pattern.search(line):
                findings.append(
                    f"{path.relative_to(ROOT)}:{number}: {label}: {raw.strip()[:120]}"
                )

        if path.suffix != ".py":
            continue

        assignment = _ASSIGN.match(line)
        if assignment:
            tainted.add(assignment.group(1))
            continue

        for name in tainted:
            if re.search(rf"\b{re.escape(name)}\s*\.\s*write_", line) or re.search(
                rf"open\(\s*{re.escape(name)}\s*,\s*['\"][wax]", line
            ):
                findings.append(
                    f"{path.relative_to(ROOT)}:{number}: "
                    f"write-via-variable '{name}': {raw.strip()[:120]}"
                )

    return findings


@pytest.mark.security
def test_no_script_generates_application_source() -> None:
    """No operational script may write into app/, terminal/, or the entry points."""
    findings: list[str] = []
    for path in _candidate_files():
        findings.extend(_scan(path))

    assert not findings, (
        "Scripts that write live application source must be relocated to "
        "archive/generators/ (Phase 1). Offenders:\n  " + "\n  ".join(findings)
    )


@pytest.mark.security
def test_archive_generators_is_excluded_from_the_scan() -> None:
    """The archive must never be scanned, or quarantined files would fail forever."""
    assert "archive" in EXCLUDED_PARTS
    assert not any(
        "archive" in path.relative_to(ROOT).parts for path in _candidate_files()
    )
