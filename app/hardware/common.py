"""Shared production primitives for hardware and EDA integrations."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class HardwareIntegrationError(RuntimeError):
    def __init__(self, component: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.component = component
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


def canonical_json(value: Any) -> bytes:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Any, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HardwareIntegrationError("configuration", f"Required JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HardwareIntegrationError("configuration", f"Invalid JSON in {path}", {"line": exc.lineno}) from exc
    if not isinstance(value, dict):
        raise HardwareIntegrationError("configuration", f"JSON root must be an object: {path}")
    return value


def require_file(path: Path, component: str, maximum_bytes: int = 128 * 1024 * 1024) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise HardwareIntegrationError(component, f"Required input is not a regular file: {resolved}")
    size = resolved.stat().st_size
    if size == 0:
        raise HardwareIntegrationError(component, f"Required input is empty: {resolved}")
    if size > maximum_bytes:
        raise HardwareIntegrationError(component, f"Input exceeds maximum size: {resolved}", {"bytes": size})
    return resolved


class CommandRunner:
    def __init__(self, *, timeout_seconds: int = 120, maximum_output_bytes: int = 4 * 1024 * 1024) -> None:
        self.timeout_seconds = timeout_seconds
        self.maximum_output_bytes = maximum_output_bytes

    def executable(self, name: str) -> str:
        location = shutil.which(name)
        if not location:
            raise HardwareIntegrationError("command", f"Required executable is unavailable: {name}")
        return location

    def run(self, command: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None) -> CommandResult:
        if not command:
            raise ValueError("command cannot be empty")
        executable = self.executable(command[0]) if os.path.sep not in command[0] else command[0]
        clean = [executable, *command[1:]]
        merged_env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
        if env:
            merged_env.update({str(k): str(v) for k, v in env.items()})
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                clean, cwd=str(cwd) if cwd else None, env=merged_env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HardwareIntegrationError("command", "External command timed out", {"command": clean, "timeout": self.timeout_seconds}) from exc
        duration = (time.perf_counter() - started) * 1000.0
        stdout = completed.stdout[: self.maximum_output_bytes].decode("utf-8", errors="replace")
        stderr = completed.stderr[: self.maximum_output_bytes].decode("utf-8", errors="replace")
        return CommandResult(tuple(clean), completed.returncode, stdout, stderr, duration)
