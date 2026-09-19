"""Purpose: Assemble an incident record for a quarantined chip and identify affected assets.
Directory: app/storage/quarantine.
Dependencies: json, pathlib, hashlib.
Connection: reads data/integrated_runs; called by scripts/incident.py. Writes nothing
to the ledger.

FB-13 lists nine incident-response steps. Quarantine, permanent rejection,
notification and fail-closed staging exist. This adds the two that can be built
honestly here: identifying which other chips share evidence with the quarantined one,
and assembling that into an auditable incident record.

Affected-asset identification uses the chain of custody already recorded. A
compromised chip's supplier, RTL digest and netlist digest are the links: any other
chip sharing one of them was produced from the same source and warrants review.

Revocation is not automated. RevokeProvenance is deployed at contract.go:121 and
reachable through FabricClient.submit, but a ledger revocation cannot be undone and a
false positive would permanently mark a record. The incident record prints the command
for an operator to run, which is a capability and a procedure rather than an
irreversible automatic action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNS_ROOT = Path("data/integrated_runs")
INCIDENT_ROOT = Path("data/incidents")


@dataclass
class Incident:
    incident_id: str
    opened_at_utc: str
    scan_id: str
    chip_id: str
    decision: str
    stopped_stage: str
    linkage: dict[str, str] = field(default_factory=dict)
    affected: list[dict[str, str]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "opened_at_utc": self.opened_at_utc,
            "trigger": {
                "scan_id": self.scan_id,
                "chip_id": self.chip_id,
                "deployment_decision": self.decision,
                "stopped_stage": self.stopped_stage,
            },
            "linkage": self.linkage,
            "affected_assets": self.affected,
            "required_actions": self.actions,
            "note": (
                "Revocation is not automated: a ledger revocation cannot be undone, "
                "and a false positive would permanently mark a record. The commands "
                "below are for an operator to run after review."
            ),
        }


def _load_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not RUNS_ROOT.is_dir():
        return runs
    for path in RUNS_ROOT.glob("*/run.json"):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return runs


def _linkage(run: dict[str, Any]) -> dict[str, str]:
    """Return the identifiers that tie a chip to others from the same source."""
    links: dict[str, str] = {}

    for stage in run.get("stages", []):
        result = stage.get("result") or {}
        metadata = (result.get("payload") or {}).get("metadata") or result

        supplier = (metadata.get("supplier") or {}).get("name")
        if supplier:
            links.setdefault("supplier", str(supplier))

        hardware = metadata.get("hardware_security") or {}
        for key in ("yosys", "verilator"):
            block = hardware.get(key) or {}
            for digest_key in ("rtl_digest", "netlist_digest", "candidate_digest"):
                value = block.get(digest_key)
                if value:
                    links.setdefault(digest_key, str(value))

    return links


def open_incident(scan_id: str) -> Incident | None:
    """Assemble an incident for a quarantined scan. Returns None if not found."""
    runs = _load_runs()
    trigger = next((r for r in runs if str(r.get("scan_id")) == scan_id), None)

    if trigger is None:
        return None

    links = _linkage(trigger)

    affected: list[dict[str, str]] = []
    for run in runs:
        if str(run.get("scan_id")) == scan_id:
            continue
        shared = {k: v for k, v in _linkage(run).items() if links.get(k) == v}
        if shared:
            affected.append(
                {
                    "scan_id": str(run.get("scan_id")),
                    "chip_id": str(run.get("chip_id")),
                    "deployment_decision": str(run.get("deployment_decision")),
                    "shared": ", ".join(sorted(shared)),
                }
            )

    incident_id = hashlib.sha256(
        f"{scan_id}{trigger.get('chip_id')}".encode()
    ).hexdigest()[:16]

    incident = Incident(
        incident_id=incident_id,
        opened_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        scan_id=scan_id,
        chip_id=str(trigger.get("chip_id")),
        decision=str(trigger.get("deployment_decision")),
        stopped_stage=str(trigger.get("stopped_stage")),
        linkage=links,
        affected=sorted(affected, key=lambda a: a["chip_id"]),
    )

    incident.actions = [
        f"Review the {len(affected)} chip(s) sharing evidence with {incident.chip_id}.",
        (
            "Revoke the ledger record once confirmed: "
            f"peer chaincode invoke -C semiconductor-channel "
            f"-n semiconductor-provenance -c "
            f'\'{{"function":"RevokeProvenance","Args":["{scan_id}","<reason-sha256>"]}}\''
        ),
        "Notify the supplier and the receiving parties. No mail transport is "
        "configured; notification is a manual step recorded here.",
        "File a regulatory report if the chip reached a controlled end use. No "
        "regulator endpoint is configured; reporting is a manual step.",
        "Record the outcome by re-running this command after the actions complete.",
    ]

    return incident


def save_incident(incident: Incident) -> Path:
    INCIDENT_ROOT.mkdir(parents=True, exist_ok=True)
    path = INCIDENT_ROOT / f"{incident.incident_id}.json"
    path.write_text(json.dumps(incident.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def list_quarantined() -> list[dict[str, str]]:
    """Quarantined runs from the integrated pipeline.

    Phase3Orchestrator.quarantine_list covers the legacy path only; the integrated
    pipeline sets run["quarantined"] and nothing collected them.
    """
    # One entry per chip, from its most recent quarantined run. Repeated scans of the
    # same chip during testing would otherwise appear as separate incidents.
    latest: dict[str, dict[str, str]] = {}

    for run in _load_runs():
        if not run.get("quarantined"):
            continue
        chip = str(run.get("chip_id"))
        entry = {
            "scan_id": str(run.get("scan_id")),
            "chip_id": chip,
            "deployment_decision": str(run.get("deployment_decision")),
            "stopped_stage": str(run.get("stopped_stage")),
            "completed_at_utc": str(run.get("completed_at_utc") or ""),
        }
        if chip not in latest or entry["completed_at_utc"] > latest[chip]["completed_at_utc"]:
            latest[chip] = entry

    return sorted(latest.values(), key=lambda r: r["chip_id"])
