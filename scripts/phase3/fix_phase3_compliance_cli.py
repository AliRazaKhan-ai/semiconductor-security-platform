"""Correct Phase 3 simulation data, CLI validation, and compliance normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")

    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def update_good_chip() -> None:
    path = ROOT / "data/chips/chip_01_good.json"
    data = read_json(path)

    data["source"] = {
        "component": "terminal",
        "operator": "ali-raza",
        "environment": "development",
    }

    data["hardware_security"] = {
        "puf": {
            "authentication_expected": True,
            "intra_device_hamming_distance": 0.03125,
            "stability_score": 0.96875,
        },
        "opentitan": {
            "secure_boot": True,
            "lifecycle_state": "PROD",
            "otp_integrity": True,
            "rom_digest_valid": True,
            "debug_locked": True,
        },
        "chipwhisperer": {
            "power_rms": 0.392,
            "power_peak_to_peak": 0.332,
            "power_spectral_entropy": 0.31,
            "em_rms": 0.37,
            "em_peak_to_peak": 0.29,
            "em_spectral_entropy": 0.28,
            "timing_jitter": 0.02,
        },
        "yosys": {
            "gate_count": 125000,
            "unused_logic_ratio": 0.01,
            "rare_net_ratio": 0.01,
            "netlist_delta_ratio": 0.0,
        },
        "verilator": {
            "simulation_passed": True,
            "test_vectors": 50000,
            "failed_vectors": 0,
            "simulation_failure_ratio": 0.0,
        },
    }

    data["supply_chain"] = {
        "digital_twin_match": True,
        "sbom_match": True,
        "custody_gap_ratio": 0.0,
        "certificate_risk": 0.02,
        "sbom_mismatch_ratio": 0.0,
    }

    data["supplier"] = {
        "supplier_id": "SUP-DE-001",
        "name": "TrustedFab Europe-1",
        "country": "DE",
        "country_risk": 0.10,
        "custody_gap_ratio": 0.0,
        "certificate_risk": 0.02,
        "sbom_mismatch_ratio": 0.0,
        "threat_intel_score": 0.02,
        "counterfeit_history": 0.0,
        "financial_distress": 0.05,
    }

    data["compliance"] = {
        "subject_to_ear": True,
        "eccn": "EAR99",
        "destination_country": "DE",
        "end_use": "regulated critical-infrastructure validation",
        "end_user_type": "regulated infrastructure operator",
        "end_user_name": "German Critical Infrastructure Test Authority",
        "technical_data_transfer": False,
        "defense_related": False,
        "specially_designed_for_military": False,
        "tags": [
            "commercial",
            "civilian",
            "critical-infrastructure",
        ],
    }

    write_json(path, data)
    print(f"Updated {path.relative_to(ROOT)}")


def normalize_other_chips() -> None:
    defaults = {
        "chip_02_trojan.json": {
            "end_user_name": "Example Telecom Operator",
            "defense_related": False,
            "specially_designed_for_military": False,
        },
        "chip_03_puf_unstable.json": {
            "end_user_name": "German Power Grid Operator",
            "defense_related": False,
            "specially_designed_for_military": False,
        },
        "chip_04_supplychain_tampered.json": {
            "end_user_name": "Example 5G Network Operator",
            "defense_related": False,
            "specially_designed_for_military": False,
        },
        "chip_05_highrisk_supplier.json": {
            "end_user_name": "Example Defense Communications Contractor",
            "defense_related": True,
            "specially_designed_for_military": True,
            "usml_category": "XI",
        },
    }

    for filename, additions in defaults.items():
        path = ROOT / "data/chips" / filename
        data = read_json(path)
        compliance = data.setdefault("compliance", {})

        if not isinstance(compliance, dict):
            raise RuntimeError(f"Invalid compliance object: {path}")

        for key, value in additions.items():
            compliance.setdefault(key, value)

        write_json(path, data)
        print(f"Normalized {path.relative_to(ROOT)}")


def patch_manage() -> None:
    path = ROOT / "manage.py"
    text = path.read_text(encoding="utf-8")

    old_item = '''    item = {
        "subject_to_ear": compliance.get(
            "subject_to_ear",
            True,
        ),
        "eccn": compliance.get("eccn", ""),
        "usml_category": compliance.get("usml_category"),
        "specially_designed_for_military": compliance.get(
            "specially_designed_for_military",
            False,
        ),
        "defense_related": compliance.get(
            "defense_related",
            False,
        ),
        "tags": compliance.get(
            "tags",
            [scenario.lower()],
        ),
    }
'''

    new_item = '''    item = {
        "subject_to_ear": bool(
            compliance.get("subject_to_ear", True)
        ),
        "eccn": str(
            compliance.get("eccn") or ""
        ).strip(),
        "specially_designed_for_military": bool(
            compliance.get(
                "specially_designed_for_military",
                False,
            )
        ),
        "defense_related": bool(
            compliance.get("defense_related", False)
        ),
        "tags": compliance.get(
            "tags",
            [scenario.lower()],
        ),
    }

    usml_category = str(
        compliance.get("usml_category") or ""
    ).strip()

    if usml_category:
        item["usml_category"] = usml_category
'''

    if old_item not in text:
        raise RuntimeError(
            "Could not locate build_compliance_payload item block"
        )

    text = text.replace(old_item, new_item, 1)

    marker = '''def command_verify_scan(args: argparse.Namespace) -> int:
    """Verify scan snapshot, events, compliance, and blockchain state."""
    scan_id = args.scan_id
'''

    replacement = '''def validate_scan_id(scan_id: str) -> str:
    """Reject documentation placeholders and malformed scan identifiers."""
    value = scan_id.strip()

    placeholders = {
        "paste-the-real-scan-id-here",
        "scan-id-returned-by-the-api",
        "actual_scan_id",
        "your_existing_scan_id",
        "<scan_id>",
    }

    if value.lower() in placeholders:
        raise CommandFailure(
            "A placeholder was supplied instead of a real scan ID. "
            "Use an ID returned by scan or scan-all."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}",
        value,
    ):
        raise CommandFailure(
            f"Invalid scan ID format: {value!r}"
        )

    return value


def command_verify_scan(args: argparse.Namespace) -> int:
    """Verify scan snapshot, events, compliance, and blockchain state."""
    scan_id = validate_scan_id(args.scan_id)
'''

    if marker not in text:
        raise RuntimeError(
            "Could not locate command_verify_scan block"
        )

    text = text.replace(marker, replacement, 1)

    export_old = '''    scan_id = args.scan_id

    source = (
'''

    export_new = '''    scan_id = validate_scan_id(args.scan_id)

    source = (
'''

    export_position = text.find(
        'def command_export_audit(args: argparse.Namespace)'
    )

    if export_position < 0:
        raise RuntimeError("command_export_audit was not found")

    before = text[:export_position]
    after = text[export_position:]

    if export_old not in after:
        raise RuntimeError(
            "Could not locate export-audit scan ID assignment"
        )

    after = after.replace(export_old, export_new, 1)
    text = before + after

    path.write_text(text, encoding="utf-8")
    print("Patched manage.py")


def patch_itar() -> None:
    candidates = [
        ROOT / "app/compliance/export_control/itar.py",
        ROOT / "app/compliance/export_control/engine.py",
    ]

    for path in candidates:
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")

        replacements = {
            'str(item.get("usml_category"))':
                'str(item.get("usml_category") or "").strip()',
            "str(item.get('usml_category'))":
                "str(item.get('usml_category') or '').strip()",
            'str(payload.get("usml_category"))':
                'str(payload.get("usml_category") or "").strip()',
            "str(payload.get('usml_category'))":
                "str(payload.get('usml_category') or '').strip()",
        }

        changed = False

        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
                changed = True

        if changed:
            path.write_text(text, encoding="utf-8")
            print(f"Normalized null USML handling in {path.relative_to(ROOT)}")


def quiet_third_party_logging() -> None:
    path = ROOT / "configs/application/logging.json"

    if not path.exists():
        return

    config = read_json(path)
    loggers = config.setdefault("loggers", {})

    if not isinstance(loggers, dict):
        loggers = {}
        config["loggers"] = loggers

    for name in (
        "web3",
        "urllib3",
        "rlp",
        "eth_utils",
        "eth_account",
    ):
        current = loggers.get(name)

        if isinstance(current, dict):
            current["level"] = "WARNING"
        else:
            loggers[name] = {
                "level": "WARNING",
                "propagate": False,
            }

    write_json(path, config)
    print("Reduced third-party blockchain logging")


def main() -> None:
    update_good_chip()
    normalize_other_chips()
    patch_manage()
    patch_itar()
    quiet_third_party_logging()


if __name__ == "__main__":
    main()
