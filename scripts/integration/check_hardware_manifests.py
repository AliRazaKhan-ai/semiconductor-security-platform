"""Validate real hardware evidence manifests for all chip simulations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHIP_ROOT = ROOT / "data" / "chips"

REQUIRED_PATH_FIELDS = (
    "opentitan_evidence",
    "side_channel_trace",
    "side_channel_reference",
    "rtl_file",
    "testbench_file",
)

REQUIRED_TEXT_FIELDS = (
    "top_module",
    "puf_identity_hash",
    "twin_id",
)


def resolve_path(value: object) -> Path:
    path = Path(str(value)).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


def read_manifest(
    simulation: dict[str, Any],
) -> dict[str, Any] | None:
    values = (
        simulation.get("hardware_manifest"),
        simulation.get("manifest"),
        (
            simulation.get("hardware_security", {}).get("manifest")
            if isinstance(simulation.get("hardware_security"), dict)
            else None
        ),
    )

    return next(
        (
            value
            for value in values
            if isinstance(value, dict)
        ),
        None,
    )


def validate_file(path: Path) -> dict[str, Any]:
    simulation = json.loads(path.read_text(encoding="utf-8"))
    manifest = read_manifest(simulation)

    errors: list[str] = []

    if manifest is None:
        return {
            "file": path.name,
            "valid": False,
            "errors": ["hardware_manifest is missing"],
        }

    for field in REQUIRED_PATH_FIELDS:
        value = manifest.get(field)

        if not value:
            errors.append(f"{field} is missing")
            continue

        resolved = resolve_path(value)

        if not resolved.is_file():
            errors.append(
                f"{field} does not exist: {resolved}"
            )

    artifacts = manifest.get("sbom_artifacts")

    if not isinstance(artifacts, list) or not artifacts:
        errors.append("sbom_artifacts must be a non-empty list")
    else:
        for index, value in enumerate(artifacts):
            resolved = resolve_path(value)

            if not resolved.is_file():
                errors.append(
                    f"sbom_artifacts[{index}] does not exist: {resolved}"
                )

    for field in REQUIRED_TEXT_FIELDS:
        if not str(manifest.get(field) or "").strip():
            errors.append(f"{field} is missing or empty")

    return {
        "file": path.name,
        "valid": not errors,
        "errors": errors,
    }


def main() -> int:
    files = sorted(CHIP_ROOT.glob("*.json"))
    results = [validate_file(path) for path in files]

    print(
        json.dumps(
            {
                "valid": all(item["valid"] for item in results),
                "files": results,
            },
            indent=2,
        )
    )

    return 0 if all(item["valid"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
