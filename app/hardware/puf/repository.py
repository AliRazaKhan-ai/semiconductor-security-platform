"""Purpose: Persist signed PUF enrollment profiles and one-time challenge state in JSON without SQL.
Directory: app/hardware/puf.
Dependencies: json, pathlib, os, existing FileLock, PUF schemas and exceptions.
Connection: Adapter uses profile files for identity and a JSONL ledger for anti-replay enforcement.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.hardware.puf.exceptions import PUFEnrollmentError, PUFIntegrityError, PUFReplayError
from app.hardware.puf.schemas import EnrollmentProfile
from app.storage.event_store.locking import FileLock

_SAFE_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_CHALLENGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _validate_identifier(value: str, pattern: re.Pattern[str], field: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"{field} contains unsupported characters")
    return value


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("incomplete PUF profile write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


class EnrollmentRepository:
    def __init__(self, root: Path, lock_root: Path) -> None:
        self.root = root
        self.lock_root = lock_root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, device_id: str) -> Path:
        identifier = _validate_identifier(device_id, _SAFE_DEVICE_ID, "device_id")
        return self.root / f"{identifier}.json"

    def _lock(self, device_id: str) -> Path:
        identifier = _validate_identifier(device_id, _SAFE_DEVICE_ID, "device_id")
        return self.lock_root / "puf-enrollment" / f"{identifier}.lock"

    def save(self, profile: EnrollmentProfile, *, replace: bool = False) -> Path:
        path = self._path(profile.device_id)
        with FileLock(self._lock(profile.device_id)):
            if path.exists() and not replace:
                raise PUFEnrollmentError("PUF device is already enrolled", {"device_id": profile.device_id})
            _atomic_json_write(path, profile.to_dict())
        return path

    def load(self, device_id: str) -> EnrollmentProfile:
        path = self._path(device_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PUFEnrollmentError("PUF enrollment profile was not found", {"device_id": device_id}) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise PUFIntegrityError("PUF enrollment profile could not be read", {"device_id": device_id}) from exc
        if not isinstance(raw, dict):
            raise PUFIntegrityError("PUF enrollment profile root must be a JSON object")
        try:
            return EnrollmentProfile.from_dict(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise PUFIntegrityError("PUF enrollment profile is malformed", {"device_id": device_id}) from exc

    def list_device_ids(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self.root.glob("*.json") if _SAFE_DEVICE_ID.fullmatch(path.stem)))


class ChallengeLedger:
    """Append-only JSONL state machine: absent -> issued -> consumed; no challenge may return to absent."""

    def __init__(self, path: Path, lock_root: Path) -> None:
        self.path = path
        self.lock_path = lock_root / "puf-challenges" / "challenge-ledger.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _read_state_unlocked(self) -> dict[str, dict[str, Any]]:
        state: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return state
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PUFIntegrityError("PUF challenge ledger contains invalid JSON", {"line": line_number}) from exc
            if not isinstance(record, dict):
                raise PUFIntegrityError("PUF challenge ledger record is not an object", {"line": line_number})
            challenge_id = str(record.get("challenge_id", ""))
            action = str(record.get("action", ""))
            if not _SAFE_CHALLENGE_ID.fullmatch(challenge_id) or action not in {"issued", "consumed"}:
                raise PUFIntegrityError("PUF challenge ledger record is malformed", {"line": line_number})
            previous = state.get(challenge_id)
            if action == "issued":
                if previous is not None:
                    raise PUFIntegrityError("PUF challenge was issued more than once", {"challenge_id": challenge_id})
            elif previous is None or previous.get("action") != "issued":
                raise PUFIntegrityError("PUF challenge was consumed without issuance", {"challenge_id": challenge_id})
            elif previous.get("consumed"):
                raise PUFIntegrityError("PUF challenge was consumed more than once", {"challenge_id": challenge_id})
            if action == "issued":
                state[challenge_id] = {**record, "consumed": False}
            else:
                state[challenge_id] = {**previous, "consumed": True, "consume_record": record}
        return state

    def _append_unlocked(self, record: dict[str, Any]) -> None:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
        descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError("incomplete PUF challenge ledger write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def status(self, challenge_id: str) -> str:
        _validate_identifier(challenge_id, _SAFE_CHALLENGE_ID, "challenge_id")
        with FileLock(self.lock_path, exclusive=False):
            record = self._read_state_unlocked().get(challenge_id)
        if record is None:
            return "AVAILABLE"
        return "CONSUMED" if record.get("consumed") else "ISSUED"

    def issue(self, challenge_id: str, device_id: str, expires_at_utc: str) -> None:
        _validate_identifier(challenge_id, _SAFE_CHALLENGE_ID, "challenge_id")
        _validate_identifier(device_id, _SAFE_DEVICE_ID, "device_id")
        with FileLock(self.lock_path):
            state = self._read_state_unlocked()
            if challenge_id in state:
                raise PUFReplayError("PUF challenge has already been issued", {"challenge_id": challenge_id})
            self._append_unlocked(
                {
                    "action": "issued",
                    "challenge_id": challenge_id,
                    "device_id": device_id,
                    "expires_at_utc": expires_at_utc,
                    "recorded_at_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
                }
            )

    def consume(self, challenge_id: str, device_id: str, response_digest: str) -> None:
        _validate_identifier(challenge_id, _SAFE_CHALLENGE_ID, "challenge_id")
        _validate_identifier(device_id, _SAFE_DEVICE_ID, "device_id")
        with FileLock(self.lock_path):
            state = self._read_state_unlocked()
            record = state.get(challenge_id)
            if record is None:
                raise PUFReplayError("PUF challenge was never issued", {"challenge_id": challenge_id})
            if record.get("device_id") != device_id:
                raise PUFReplayError("PUF challenge was issued for a different device", {"challenge_id": challenge_id})
            if record.get("consumed"):
                raise PUFReplayError("PUF challenge response was replayed", {"challenge_id": challenge_id})
            self._append_unlocked(
                {
                    "action": "consumed",
                    "challenge_id": challenge_id,
                    "device_id": device_id,
                    "response_digest": response_digest,
                    "recorded_at_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
                }
            )

    def counts(self) -> dict[str, int]:
        with FileLock(self.lock_path, exclusive=False):
            state = self._read_state_unlocked()
        issued = sum(not value.get("consumed") for value in state.values())
        consumed = sum(bool(value.get("consumed")) for value in state.values())
        return {"issued": issued, "consumed": consumed, "total": len(state)}
