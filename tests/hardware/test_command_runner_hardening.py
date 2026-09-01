"""Security regression tests for external hardware command execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.hardware.common import (
    CommandRunner,
    HardwareIntegrationError,
)


def test_parent_environment_secret_is_not_inherited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "SEMISURE_TEST_SECRET",
        "must-not-reach-child",
    )

    result = CommandRunner().run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "print(os.getenv("
                "'SEMISURE_TEST_SECRET', 'ABSENT'))"
            ),
        ],
        cwd=tmp_path,
    )

    assert result.succeeded is True
    assert result.stdout.strip() == "ABSENT"


def test_explicit_environment_override_is_available(
    tmp_path: Path,
) -> None:
    result = CommandRunner().run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "print(os.getenv("
                "'SEMISURE_EXPLICIT_VALUE', 'ABSENT'))"
            ),
        ],
        cwd=tmp_path,
        env={
            "SEMISURE_EXPLICIT_VALUE": "present",
        },
    )

    assert result.succeeded is True
    assert result.stdout.strip() == "present"


def test_working_directory_controls_temp_and_file_permissions(
    tmp_path: Path,
) -> None:
    code = (
        "import os; "
        "from pathlib import Path; "
        "artifact = Path('eda-artifact.txt'); "
        "artifact.write_text('evidence', encoding='utf-8'); "
        "print(Path.cwd()); "
        "print(os.environ.get('TMPDIR')); "
        "print(oct(artifact.stat().st_mode & 0o777))"
    )

    result = CommandRunner().run(
        [
            sys.executable,
            "-c",
            code,
        ],
        cwd=tmp_path,
    )

    assert result.succeeded is True

    lines = result.stdout.splitlines()

    assert lines[0] == str(tmp_path.resolve())
    assert lines[1] == str(tmp_path.resolve())
    assert lines[2] == "0o600"


def test_non_directory_working_directory_is_rejected(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "not-a-directory"
    invalid.write_text(
        "not a directory",
        encoding="utf-8",
    )

    with pytest.raises(
        HardwareIntegrationError,
        match="working directory is not a directory",
    ):
        CommandRunner().run(
            [
                sys.executable,
                "-c",
                "print('must-not-run')",
            ],
            cwd=invalid,
        )


def test_command_timeout_remains_enforced(
    tmp_path: Path,
) -> None:
    runner = CommandRunner(
        timeout_seconds=0.1,
    )

    with pytest.raises(
        HardwareIntegrationError,
        match="External command timed out",
    ):
        runner.run(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ],
            cwd=tmp_path,
        )


def test_retained_output_remains_bounded(
    tmp_path: Path,
) -> None:
    runner = CommandRunner(
        maximum_output_bytes=16,
    )

    result = runner.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('A' * 100); "
                "print('B' * 100, file=sys.stderr)"
            ),
        ],
        cwd=tmp_path,
    )

    assert result.succeeded is True
    assert len(result.stdout.encode("utf-8")) <= 16
    assert len(result.stderr.encode("utf-8")) <= 16
