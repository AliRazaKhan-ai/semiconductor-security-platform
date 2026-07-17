"""Purpose: Expose terminal-only PUF enrollment and authentication operations.
Directory: app/hardware/puf.
Dependencies: argparse, JSON, pathlib, PUF adapter and schemas.
Connection: Terminal creates challenges and responses; dashboard remains read-only and receives backend events only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.exceptions import PUFError
from app.hardware.puf.schemas import PUFChallenge, PUFEnvironment, PUFResponse


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.hardware.puf.cli",
        description="Terminal-only hybrid PUF simulator and authentication service",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)

    enroll = commands.add_parser("enroll", help="Enroll a simulated physical device")
    enroll.add_argument("--device-id", required=True)
    enroll.add_argument("--replace", action="store_true")

    challenge = commands.add_parser("challenge", help="Issue one unused authentication challenge")
    challenge.add_argument("--device-id", required=True)
    challenge.add_argument("--output", type=Path, required=True)

    respond = commands.add_parser("respond", help="Generate a physical response at the terminal")
    respond.add_argument("--device-id", required=True)
    respond.add_argument("--challenge", type=Path, required=True)
    respond.add_argument("--output", type=Path, required=True)
    respond.add_argument("--temperature-c", type=float, default=25.0)
    respond.add_argument("--voltage-v", type=float, default=1.0)
    respond.add_argument("--age-hours", type=float, default=0.0)

    authenticate = commands.add_parser("authenticate", help="Verify a one-time challenge response")
    authenticate.add_argument("--device-id", required=True)
    authenticate.add_argument("--challenge", type=Path, required=True)
    authenticate.add_argument("--response", type=Path, required=True)

    status = commands.add_parser("status", help="Show enrollment and challenge-bank status")
    status.add_argument("--device-id", required=True)

    commands.add_parser("health", help="Show PUF service health")

    demo = commands.add_parser("demo", help="Run genuine-device and clone-rejection demonstration")
    demo.add_argument("--device-id", required=True)
    demo.add_argument("--clone-device-id", default="CLONE-DEVICE-001")
    demo.add_argument("--replace", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    adapter = PUFAdapter.from_project(args.project_root)
    if args.command == "enroll":
        profile = adapter.enroll_device(args.device_id, replace=args.replace)
        _print(
            {
                "status": "ENROLLED",
                "device_id": profile.device_id,
                "identity_hash": profile.identity_hash,
                "challenge_count": len(profile.templates),
                "config_fingerprint": profile.config_fingerprint,
            }
        )
        return 0
    if args.command == "challenge":
        value = adapter.issue_challenge(args.device_id)
        _write_json(args.output, value.to_dict())
        _print({"status": "CHALLENGE_ISSUED", "challenge_id": value.challenge_id, "output": str(args.output)})
        return 0
    if args.command == "respond":
        challenge = PUFChallenge.from_dict(_read_json(args.challenge))
        response = adapter.simulate_response(
            args.device_id,
            challenge,
            PUFEnvironment(
                temperature_c=args.temperature_c,
                voltage_v=args.voltage_v,
                age_hours=args.age_hours,
            ),
        )
        _write_json(args.output, response.to_dict())
        _print(
            {
                "status": "RESPONSE_GENERATED",
                "challenge_id": challenge.challenge_id,
                "overall_reliability": response.overall_reliability,
                "output": str(args.output),
            }
        )
        return 0
    if args.command == "authenticate":
        challenge = PUFChallenge.from_dict(_read_json(args.challenge))
        response = PUFResponse.from_dict(_read_json(args.response))
        result = adapter.authenticate(args.device_id, challenge, response)
        _print(result.to_dict())
        return 0 if result.accepted else 2
    if args.command == "status":
        _print(adapter.status(args.device_id))
        return 0
    if args.command == "health":
        _print(adapter.health())
        return 0
    if args.command == "demo":
        adapter.enroll_device(args.device_id, replace=args.replace)
        genuine_challenge = adapter.issue_challenge(args.device_id)
        genuine_response = adapter.simulate_response(args.device_id, genuine_challenge)
        genuine_result = adapter.authenticate(args.device_id, genuine_challenge, genuine_response)

        clone_challenge = adapter.issue_challenge(args.device_id)
        clone_response = adapter.simulator(args.clone_device_id).respond(
            clone_challenge,
            PUFEnvironment(
                temperature_c=adapter.config.environment.nominal_temperature_c,
                voltage_v=adapter.config.environment.nominal_voltage_v,
            ),
            sample_count=adapter.config.authentication.response_samples,
        )
        clone_result = adapter.authenticate(args.device_id, clone_challenge, clone_response)
        _print(
            {
                "genuine": genuine_result.to_dict(),
                "clone": clone_result.to_dict(),
                "anti_cloning_passed": genuine_result.accepted and not clone_result.accepted,
            }
        )
        return 0 if genuine_result.accepted and not clone_result.accepted else 3
    raise RuntimeError("unreachable command")


def main() -> None:
    parser = build_parser()
    try:
        raise SystemExit(run(parser.parse_args()))
    except (PUFError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _print(
            {
                "status": "ERROR",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
