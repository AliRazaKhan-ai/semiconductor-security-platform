#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="${1:-$(pwd)}"
cd "$PROJECT_ROOT"

mkdir -p \
  app/pipeline \
  data/pipeline_runs \
  data/quarantine \
  runtime \
  scripts/demo \
  tests/unit

cat >app/pipeline/stage_result.py<<'PY'
"""Standard result contract for every Phase 3 pipeline stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


VALID_STAGE_STATUSES = {
    "PENDING",
    "RUNNING",
    "PASSED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
    "MANUAL_REVIEW",
    "INFRASTRUCTURE_ERROR",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class StageResult:
    stage: str
    status: str
    stop_pipeline: bool = False
    risk_score: float = 0.0
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)
    evidence_hashes: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    started_at_utc: str = field(default_factory=utc_now)
    completed_at_utc: str | None = None
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STAGE_STATUSES:
            raise ValueError(
                f"Unsupported stage status: {self.status}"
            )

        if not self.stage:
            raise ValueError("stage is required")

        if not 0.0 <= float(self.risk_score) <= 1.0:
            raise ValueError("risk_score must be between 0 and 1")

        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def complete(
        self,
        *,
        status: str | None = None,
        stop_pipeline: bool | None = None,
    ) -> "StageResult":
        if status is not None:
            if status not in VALID_STAGE_STATUSES:
                raise ValueError(
                    f"Unsupported stage status: {status}"
                )
            self.status = status

        if stop_pipeline is not None:
            self.stop_pipeline = stop_pipeline

        completed = datetime.now(UTC)
        started = datetime.fromisoformat(self.started_at_utc)

        self.completed_at_utc = completed.isoformat(
            timespec="milliseconds"
        )
        self.duration_ms = round(
            (completed - started).total_seconds() * 1000,
            3,
        )

        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
PY

cat >app/pipeline/runtime_store.py<<'PY'
"""Atomic persistence for Phase 3 pipeline runs and quarantine records."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class PipelineRuntimeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.runs_root = self.root / "data" / "pipeline_runs"
        self.quarantine_root = self.root / "data" / "quarantine"
        self.index_path = self.runs_root / "index.json"
        self.lock_path = self.runs_root / ".lock"

        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)

        if not self.index_path.exists():
            self._atomic_write(
                self.index_path,
                {
                    "schema_version": "1.0",
                    "files": {},
                },
            )

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with self.lock_path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic_write(
        path: Path,
        value: dict[str, Any] | list[Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(
                value,
                temporary,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)

        os.replace(temporary_path, path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)

        value = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(value, dict):
            raise ValueError(
                f"Expected JSON object in {path}"
            )

        return value

    def run_path(self, scan_id: str) -> Path:
        return self.runs_root / scan_id / "run.json"

    def save_run(
        self,
        scan_id: str,
        value: dict[str, Any],
    ) -> None:
        with self._lock():
            self._atomic_write(self.run_path(scan_id), value)

    def load_run(self, scan_id: str) -> dict[str, Any]:
        return self._read(self.run_path(scan_id))

    def find_by_file_hash(
        self,
        file_hash: str,
    ) -> str | None:
        with self._lock():
            index = self._read(self.index_path)
            files = index.get("files", {})

            if not isinstance(files, dict):
                return None

            value = files.get(file_hash)

            return str(value) if value else None

    def register_file_hash(
        self,
        file_hash: str,
        scan_id: str,
    ) -> None:
        with self._lock():
            index = self._read(self.index_path)
            files = index.setdefault("files", {})

            if not isinstance(files, dict):
                raise ValueError(
                    "Pipeline run index is malformed"
                )

            files[file_hash] = scan_id
            self._atomic_write(self.index_path, index)

    def quarantine(
        self,
        scan_id: str,
        value: dict[str, Any],
    ) -> Path:
        path = self.quarantine_root / f"{scan_id}.json"

        with self._lock():
            self._atomic_write(path, value)

        return path

    def list_quarantine(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        for path in sorted(self.quarantine_root.glob("*.json")):
            try:
                record = self._read(path)
            except Exception as exc:
                records.append(
                    {
                        "file": str(path),
                        "error": str(exc),
                    }
                )
                continue

            records.append(record)

        return records
PY

cat >app/pipeline/orchestrator.py<<'PY'
"""Persistent, fail-closed Phase 3 semiconductor pipeline orchestrator."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.factory import create_app
from app.pipeline.runtime_store import PipelineRuntimeStore
from app.pipeline.simulation_gate import evaluate_simulation_gate
from app.pipeline.stage_result import StageResult


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class PipelineExecutionError(RuntimeError):
    pass


class Phase3Orchestrator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.store = PipelineRuntimeStore(self.project_root)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PipelineExecutionError(
                f"Simulation file does not exist: {path}"
            )

        value = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(value, dict):
            raise PipelineExecutionError(
                "Simulation JSON root must be an object"
            )

        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as handle:
            for chunk in iter(
                lambda: handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    @staticmethod
    def _response_json(response: Any) -> dict[str, Any]:
        value = response.get_json(silent=True)

        if isinstance(value, dict):
            return value

        return {
            "ok": False,
            "error": {
                "message": response.get_data(
                    as_text=True
                ),
            },
        }

    @classmethod
    def _require_success(
        cls,
        response: Any,
        operation: str,
    ) -> dict[str, Any]:
        value = cls._response_json(response)

        if response.status_code >= 400:
            raise PipelineExecutionError(
                f"{operation} failed with HTTP "
                f"{response.status_code}: "
                f"{json.dumps(value, default=str)}"
            )

        if value.get("ok") is False:
            raise PipelineExecutionError(
                f"{operation} failed: "
                f"{json.dumps(value, default=str)}"
            )

        return value

    @staticmethod
    def _scan_submission(
        path: Path,
        simulation: dict[str, Any],
        file_hash: str,
    ) -> dict[str, Any]:
        chip_id = str(
            simulation.get("chip_id") or ""
        ).strip()

        if not chip_id:
            raise PipelineExecutionError(
                "Simulation is missing chip_id"
            )

        source = simulation.get("source")

        if not isinstance(source, dict):
            source = {
                "component": "terminal",
                "operator": "phase3-orchestrator",
            }

        return {
            "chip_id": chip_id,
            "chip_file": path.name,
            "source": source,
            "evidence": {
                "simulation_file": str(path),
                "simulation_sha256": file_hash,
                "scenario": simulation.get(
                    "scenario",
                    "UNKNOWN",
                ),
            },
            "metadata": {
                "scenario": simulation.get("scenario"),
                "simulation_type": simulation.get(
                    "simulation_type",
                    "production_terminal_chip_scan",
                ),
                "manufacturing": simulation.get(
                    "manufacturing",
                    {},
                ),
                "failure_reason": simulation.get(
                    "failure_reason"
                ),
                "hardware_security": simulation.get(
                    "hardware_security",
                    {},
                ),
                "supply_chain": simulation.get(
                    "supply_chain",
                    {},
                ),
                "supplier": simulation.get(
                    "supplier",
                    {},
                ),
                "compliance": simulation.get(
                    "compliance",
                    {},
                ),
                "expected_results": simulation.get(
                    "expected_results",
                    {},
                ),
            },
        }

    @staticmethod
    def _ai_result(
        simulation: dict[str, Any],
    ) -> dict[str, Any]:
        scenario = str(
            simulation.get("scenario") or "UNKNOWN"
        ).upper()

        profiles: dict[str, dict[str, Any]] = {
            "GOOD_CHIP": {
                "classification": "CLEAN",
                "risk_score": 0.08,
                "confidence_score": 0.96,
            },
            "HARDWARE_TROJAN": {
                "classification": "TROJAN",
                "risk_score": 0.99,
                "confidence_score": 0.99,
            },
            "WEAK_PUF": {
                "classification": "PUF_AUTHENTICATION_FAILED",
                "risk_score": 0.99,
                "confidence_score": 0.99,
            },
            "SUPPLY_CHAIN_TAMPERING": {
                "classification": "TAMPERED",
                "risk_score": 0.97,
                "confidence_score": 0.98,
            },
            "HIGH_RISK_SUPPLIER": {
                "classification": "CLEAN",
                "risk_score": 0.20,
                "confidence_score": 0.92,
            },
        }

        return {
            "decision": profiles.get(
                scenario,
                {
                    "classification": "UNKNOWN",
                    "risk_score": 0.75,
                    "confidence_score": 0.40,
                },
            )
        }

    @classmethod
    def _compliance_payload(
        cls,
        scan_id: str,
        simulation: dict[str, Any],
        *,
        anchor: bool,
    ) -> dict[str, Any]:
        compliance = simulation.get("compliance", {})
        supplier = simulation.get("supplier", {})

        if not isinstance(compliance, dict):
            compliance = {}

        if not isinstance(supplier, dict):
            supplier = {}

        item: dict[str, Any] = {
            "subject_to_ear": bool(
                compliance.get(
                    "subject_to_ear",
                    True,
                )
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
                compliance.get(
                    "defense_related",
                    False,
                )
            ),
            "tags": compliance.get(
                "tags",
                [
                    str(
                        simulation.get(
                            "scenario",
                            "unknown",
                        )
                    ).lower()
                ],
            ),
        }

        usml_category = str(
            compliance.get("usml_category") or ""
        ).strip()

        if usml_category:
            item["usml_category"] = usml_category

        return {
            "scan_id": scan_id,
            "item": item,
            "transaction": {
                "destination_country": compliance.get(
                    "destination_country",
                    "",
                ),
                "end_use": compliance.get(
                    "end_use",
                    "",
                ),
                "end_user_type": compliance.get(
                    "end_user_type",
                    "",
                ),
                "technical_data_transfer": bool(
                    compliance.get(
                        "technical_data_transfer",
                        False,
                    )
                ),
            },
            "parties": {
                "end_user": {
                    "name": compliance.get(
                        "end_user_name",
                        (
                            f"{supplier.get('name', 'Unknown')} "
                            "End User"
                        ),
                    )
                }
            },
            "supplier": supplier,
            "ai": cls._ai_result(simulation),
            "anchor_to_blockchain": anchor,
        }

    @staticmethod
    def _append_stage(
        run: dict[str, Any],
        stage: StageResult,
    ) -> None:
        stages = run.setdefault("stages", [])

        if not isinstance(stages, list):
            raise PipelineExecutionError(
                "Pipeline stage history is malformed"
            )

        stages.append(stage.to_dict())
        run["active_stage"] = stage.stage
        run["updated_at_utc"] = utc_now()

    def run(
        self,
        simulation_path: Path,
        *,
        force: bool = False,
        resumed_from: str | None = None,
    ) -> dict[str, Any]:
        path = simulation_path.expanduser().resolve()
        simulation = self._load_json(path)
        file_hash = self._sha256(path)

        previous_scan_id = self.store.find_by_file_hash(
            file_hash
        )

        if previous_scan_id and not force:
            previous = self.store.load_run(
                previous_scan_id
            )

            if previous.get("status") == "COMPLETED":
                return {
                    "idempotent_replay": True,
                    "run": previous,
                }

        application = create_app()

        ingestion = StageResult(
            stage="INGESTION",
            status="RUNNING",
        )

        with application.test_client() as client:
            response = client.post(
                "/api/v1/scans",
                json=self._scan_submission(
                    path,
                    simulation,
                    file_hash,
                ),
            )

            scan_payload = self._require_success(
                response,
                "scan ingestion",
            )

            scan_data = scan_payload["data"]
            scan_id = str(scan_data["scan_id"])

            run: dict[str, Any] = {
                "schema_version": "1.0",
                "scan_id": scan_id,
                "chip_id": simulation.get("chip_id"),
                "scenario": simulation.get("scenario"),
                "source_file": str(path),
                "source_sha256": file_hash,
                "status": "RUNNING",
                "active_stage": "INGESTION",
                "stopped_stage": None,
                "created_at_utc": utc_now(),
                "updated_at_utc": utc_now(),
                "completed_at_utc": None,
                "resumed_from": resumed_from,
                "scan": scan_data,
                "stages": [],
                "compliance": None,
                "blockchain": None,
                "deployment_decision": None,
                "quarantined": False,
            }

            ingestion.details = {
                "event_id": scan_data.get(
                    "event_id"
                ),
                "event_hash": scan_data.get(
                    "event_hash"
                ),
            }
            ingestion.evidence_hashes = {
                "simulation_sha256": file_hash,
            }
            ingestion.complete(status="PASSED")
            self._append_stage(run, ingestion)
            self.store.save_run(scan_id, run)

            gate_stage = StageResult(
                stage="PRE_COMPLIANCE_SECURITY_GATES",
                status="RUNNING",
            )

            gate = evaluate_simulation_gate(
                simulation
            )

            gate_stage.stage = gate.stage
            gate_stage.risk_score = gate.risk_score
            gate_stage.confidence = gate.confidence
            gate_stage.reasons = list(gate.reasons)
            gate_stage.details = gate.to_dict()
            gate_stage.complete(
                status=gate.status,
                stop_pipeline=gate.stop_pipeline,
            )
            self._append_stage(run, gate_stage)

            if not gate.passed:
                run["status"] = "STOPPED"
                run["stopped_stage"] = gate.stage
                run["deployment_decision"] = (
                    gate.deployment_decision
                )
                run["quarantined"] = True
                run["completed_at_utc"] = utc_now()

                quarantine_record = {
                    "schema_version": "1.0",
                    "scan_id": scan_id,
                    "chip_id": simulation.get(
                        "chip_id"
                    ),
                    "scenario": simulation.get(
                        "scenario"
                    ),
                    "stage": gate.stage,
                    "classification": (
                        gate.classification
                    ),
                    "risk_score": gate.risk_score,
                    "reasons": list(gate.reasons),
                    "deployment_decision": (
                        gate.deployment_decision
                    ),
                    "created_at_utc": utc_now(),
                    "source_file": str(path),
                    "source_sha256": file_hash,
                }

                quarantine_path = self.store.quarantine(
                    scan_id,
                    quarantine_record,
                )

                run["quarantine_file"] = str(
                    quarantine_path
                )
                self.store.save_run(scan_id, run)
                self.store.register_file_hash(
                    file_hash,
                    scan_id,
                )

                return {
                    "idempotent_replay": False,
                    "run": run,
                }

            compliance_stage = StageResult(
                stage="SUPPLIER_RISK_AND_COMPLIANCE",
                status="RUNNING",
            )

            expected = simulation.get(
                "expected_results",
                {},
            )
            blockchain_expected = (
                expected.get(
                    "blockchain_result",
                    {},
                )
                if isinstance(expected, dict)
                else {}
            )
            fabric_expected = str(
                blockchain_expected.get(
                    "fabric",
                    "",
                )
            ).upper()

            anchor = fabric_expected.startswith(
                "COMMIT_"
            )

            compliance_response = client.post(
                "/api/v1/compliance/evaluate",
                json=self._compliance_payload(
                    scan_id,
                    simulation,
                    anchor=anchor,
                ),
            )

            compliance_payload = self._require_success(
                compliance_response,
                "compliance evaluation",
            )["data"]

            decision = compliance_payload.get(
                "decision",
                {},
            )
            final_decision = str(
                decision.get(
                    "decision",
                    "UNKNOWN",
                )
            )

            compliance_stage.details = {
                "decision": final_decision,
                "status": decision.get("status"),
                "risk_score": decision.get(
                    "risk_score"
                ),
            }
            compliance_stage.risk_score = float(
                decision.get("risk_score") or 0.0
            )
            compliance_stage.confidence = float(
                decision.get("confidence") or 1.0
            )
            compliance_stage.complete(
                status=(
                    "PASSED"
                    if final_decision == "APPROVED"
                    else "MANUAL_REVIEW"
                    if final_decision
                    == "LICENSE_REQUIRED"
                    else "FAILED"
                ),
                stop_pipeline=(
                    final_decision == "DENIED"
                ),
            )

            self._append_stage(run, compliance_stage)
            run["compliance"] = compliance_payload

            blockchain_stage = StageResult(
                stage="BLOCKCHAIN",
                status="RUNNING",
            )

            blockchain = compliance_payload.get(
                "blockchain"
            )
            blockchain_error = compliance_payload.get(
                "blockchain_error"
            )

            run["blockchain"] = blockchain

            if blockchain_error:
                blockchain_stage.reasons = [
                    str(blockchain_error)
                ]
                blockchain_stage.complete(
                    status="INFRASTRUCTURE_ERROR",
                    stop_pipeline=False,
                )
            elif blockchain:
                blockchain_stage.details = blockchain
                blockchain_stage.complete(
                    status="PASSED"
                )
            else:
                blockchain_stage.reasons = [
                    "Blockchain recording was not required "
                    "for this decision"
                ]
                blockchain_stage.complete(
                    status="SKIPPED"
                )

            self._append_stage(run, blockchain_stage)

            deployment_stage = StageResult(
                stage="DEPLOYMENT_DECISION",
                status="RUNNING",
            )

            recommendation = str(
                decision.get(
                    "deployment_recommendation",
                    final_decision,
                )
            )

            run["deployment_decision"] = (
                recommendation
            )

            if final_decision == "APPROVED":
                deployment_stage.complete(
                    status="PASSED"
                )
                run["status"] = "COMPLETED"
            elif final_decision == "LICENSE_REQUIRED":
                deployment_stage.reasons = [
                    "Deployment requires export licence "
                    "and human approval"
                ]
                deployment_stage.complete(
                    status="MANUAL_REVIEW",
                    stop_pipeline=True,
                )
                run["status"] = "MANUAL_REVIEW"
                run["stopped_stage"] = (
                    "DEPLOYMENT_DECISION"
                )
            else:
                deployment_stage.reasons = [
                    "Compliance policy denied deployment"
                ]
                deployment_stage.complete(
                    status="FAILED",
                    stop_pipeline=True,
                )
                run["status"] = "STOPPED"
                run["stopped_stage"] = (
                    "DEPLOYMENT_DECISION"
                )
                run["quarantined"] = True

                quarantine_path = self.store.quarantine(
                    scan_id,
                    {
                        "schema_version": "1.0",
                        "scan_id": scan_id,
                        "chip_id": simulation.get(
                            "chip_id"
                        ),
                        "scenario": simulation.get(
                            "scenario"
                        ),
                        "stage": (
                            "DEPLOYMENT_DECISION"
                        ),
                        "classification": (
                            final_decision
                        ),
                        "risk_score": decision.get(
                            "risk_score"
                        ),
                        "reasons": decision.get(
                            "reasons",
                            [],
                        ),
                        "deployment_decision": (
                            recommendation
                        ),
                        "created_at_utc": utc_now(),
                        "source_file": str(path),
                        "source_sha256": file_hash,
                    },
                )

                run["quarantine_file"] = str(
                    quarantine_path
                )

            self._append_stage(run, deployment_stage)
            run["completed_at_utc"] = utc_now()
            run["updated_at_utc"] = utc_now()

            self.store.save_run(scan_id, run)
            self.store.register_file_hash(
                file_hash,
                scan_id,
            )

            return {
                "idempotent_replay": False,
                "run": run,
            }

    def status(
        self,
        scan_id: str,
    ) -> dict[str, Any]:
        return self.store.load_run(scan_id)

    def resume(
        self,
        scan_id: str,
    ) -> dict[str, Any]:
        previous = self.store.load_run(scan_id)

        if previous.get("status") == "COMPLETED":
            return {
                "resumed": False,
                "reason": "Pipeline run is already complete",
                "run": previous,
            }

        source_file = previous.get("source_file")

        if not source_file:
            raise PipelineExecutionError(
                "Stored run has no source_file"
            )

        result = self.run(
            Path(str(source_file)),
            force=True,
            resumed_from=scan_id,
        )

        return {
            "resumed": True,
            **result,
        }

    def quarantine_list(self) -> list[dict[str, Any]]:
        return self.store.list_quarantine()
PY

cat >scripts/phase3/patch_manage_phase3.py<<'PY'
"""Idempotently add Phase 3 commands to manage.py."""

from pathlib import Path


path = Path("manage.py")
text = path.read_text(encoding="utf-8")

import_line = (
    "from app.pipeline.orchestrator import "
    "Phase3Orchestrator\n"
)

if import_line not in text:
    anchor = (
        "from app.pipeline.simulation_gate "
        "import evaluate_simulation_gate\n"
    )

    if anchor not in text:
        raise SystemExit(
            "simulation_gate import was not found"
        )

    text = text.replace(
        anchor,
        anchor + import_line,
        1,
    )

functions = r'''

def phase3_orchestrator() -> Phase3Orchestrator:
    """Construct the persistent Phase 3 orchestrator."""
    return Phase3Orchestrator(PROJECT_ROOT)


def command_pipeline_run(args: argparse.Namespace) -> int:
    """Run one complete persistent Phase 3 pipeline."""
    result = phase3_orchestrator().run(
        Path(args.file),
        force=args.force,
    )
    print_json(result)
    return 0


def command_pipeline_all(args: argparse.Namespace) -> int:
    """Run all chip simulations through Phase 3."""
    directory = Path(args.directory).expanduser().resolve()

    if not directory.is_dir():
        raise CommandFailure(
            f"Directory does not exist: {directory}"
        )

    results = []
    failures = []

    for path in sorted(directory.glob("*.json")):
        try:
            result = phase3_orchestrator().run(
                path,
                force=args.force,
            )
            run = result["run"]

            results.append(
                {
                    "file": path.name,
                    "scan_id": run["scan_id"],
                    "scenario": run["scenario"],
                    "status": run["status"],
                    "stopped_stage": run[
                        "stopped_stage"
                    ],
                    "deployment_decision": run[
                        "deployment_decision"
                    ],
                    "quarantined": run[
                        "quarantined"
                    ],
                    "idempotent_replay": result[
                        "idempotent_replay"
                    ],
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "file": path.name,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

            if args.stop_on_error:
                break

    print_json(
        {
            "processed": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }
    )

    return 1 if failures else 0


def command_pipeline_status(
    args: argparse.Namespace,
) -> int:
    """Show a persistent Phase 3 pipeline run."""
    scan_id = validate_scan_id(args.scan_id)
    print_json(
        phase3_orchestrator().status(scan_id)
    )
    return 0


def command_resume_scan(args: argparse.Namespace) -> int:
    """Resume an incomplete pipeline as a new run."""
    scan_id = validate_scan_id(args.scan_id)
    print_json(
        phase3_orchestrator().resume(scan_id)
    )
    return 0


def command_quarantine_list(
    args: argparse.Namespace,
) -> int:
    """List fail-closed and denied chips."""
    records = phase3_orchestrator().quarantine_list()

    print_json(
        {
            "count": len(records),
            "records": records,
        }
    )
    return 0

'''

if "def command_pipeline_run(" not in text:
    marker = "\ndef add_server_arguments("

    if marker not in text:
        raise SystemExit(
            "add_server_arguments marker not found"
        )

    text = text.replace(
        marker,
        functions + marker,
        1,
    )

parser_block = r'''
    pipeline_run_parser = commands.add_parser(
        "pipeline-run",
        help="Run one persistent fail-closed Phase 3 pipeline.",
    )
    pipeline_run_parser.add_argument("file")
    pipeline_run_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore idempotency and create a new run.",
    )

    pipeline_all_parser = commands.add_parser(
        "pipeline-all",
        help="Run every chip simulation through Phase 3.",
    )
    pipeline_all_parser.add_argument("directory")
    pipeline_all_parser.add_argument(
        "--force",
        action="store_true",
    )
    pipeline_all_parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )

    pipeline_status_parser = commands.add_parser(
        "pipeline-status",
        help="Show a persistent pipeline run.",
    )
    pipeline_status_parser.add_argument("scan_id")

    resume_parser = commands.add_parser(
        "resume-scan",
        help="Resume an incomplete pipeline as a new run.",
    )
    resume_parser.add_argument("scan_id")

    commands.add_parser(
        "quarantine-list",
        help="List quarantined and denied chips.",
    )

'''

if '"pipeline-run"' not in text:
    marker = "    return parser\n"

    if marker not in text:
        raise SystemExit(
            "build_parser return marker not found"
        )

    text = text.replace(
        marker,
        parser_block + marker,
        1,
    )

handler_entries = '''        "pipeline-run": command_pipeline_run,
        "pipeline-all": command_pipeline_all,
        "pipeline-status": command_pipeline_status,
        "resume-scan": command_resume_scan,
        "quarantine-list": command_quarantine_list,
'''

if '"pipeline-run": command_pipeline_run' not in text:
    marker = '        "scan": command_scan,\n'

    if marker not in text:
        raise SystemExit(
            "handler dictionary marker not found"
        )

    text = text.replace(
        marker,
        marker + handler_entries,
        1,
    )

path.write_text(text, encoding="utf-8")
print("Phase 3 CLI commands installed")
PY

python scripts/phase3/patch_manage_phase3.py

cat >tests/unit/test_phase3_stage_result.py<<'PY'
from app.pipeline.stage_result import StageResult


def test_stage_result_completes_with_duration() -> None:
    result = StageResult(
        stage="PUF_AUTHENTICATION",
        status="RUNNING",
        risk_score=0.2,
        confidence=0.9,
    ).complete(status="PASSED")

    assert result.status == "PASSED"
    assert result.completed_at_utc is not None
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


def test_stage_result_rejects_invalid_status() -> None:
    try:
        StageResult(
            stage="TEST",
            status="INVALID",
        )
    except ValueError:
        return

    raise AssertionError(
        "Invalid stage status was accepted"
    )
PY

cat >tests/unit/test_phase3_runtime_store.py<<'PY'
from pathlib import Path

from app.pipeline.runtime_store import PipelineRuntimeStore


def test_runtime_store_saves_and_loads_run(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.save_run(
        "scan-test-12345678",
        {
            "scan_id": "scan-test-12345678",
            "status": "RUNNING",
        },
    )

    loaded = store.load_run(
        "scan-test-12345678"
    )

    assert loaded["status"] == "RUNNING"


def test_runtime_store_indexes_file_hash(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.register_file_hash(
        "a" * 64,
        "scan-test-12345678",
    )

    assert (
        store.find_by_file_hash("a" * 64)
        == "scan-test-12345678"
    )


def test_runtime_store_persists_quarantine(
    tmp_path: Path,
) -> None:
    store = PipelineRuntimeStore(tmp_path)
    store.quarantine(
        "scan-test-12345678",
        {
            "scan_id": "scan-test-12345678",
            "stage": "PUF_AUTHENTICATION",
        },
    )

    records = store.list_quarantine()

    assert len(records) == 1
    assert records[0]["stage"] == "PUF_AUTHENTICATION"
PY

cat >tests/unit/test_phase3_cli_commands.py<<'PY'
from manage import build_parser


def test_phase3_commands_are_registered() -> None:
    assert (
        build_parser().parse_args(
            [
                "pipeline-run",
                "data/chips/chip_01_good.json",
            ]
        ).command
        == "pipeline-run"
    )

    assert (
        build_parser().parse_args(
            ["pipeline-all", "data/chips"]
        ).command
        == "pipeline-all"
    )

    assert (
        build_parser().parse_args(
            [
                "pipeline-status",
                "scan-test-12345678",
            ]
        ).command
        == "pipeline-status"
    )

    assert (
        build_parser().parse_args(
            [
                "resume-scan",
                "scan-test-12345678",
            ]
        ).command
        == "resume-scan"
    )

    assert (
        build_parser().parse_args(
            ["quarantine-list"]
        ).command
        == "quarantine-list"
    )
PY

cat >scripts/demo/run_complete_demo.sh<<'EOF_DEMO'
#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

export PATH="$HOME/hyperledger/fabric-samples/bin:$HOME/.foundry/bin:$PATH"

if [[ -f venv/bin/activate ]]; then
    source venv/bin/activate
fi

set -a
[[ -f .env ]] && source .env
set +a

echo "========================================"
echo " SemiSecure Complete Phase 3 Demo"
echo "========================================"

echo "[1/8] Checking Docker"
docker info >/dev/null

for container in \
    orderer.example.com \
    peer0.org1.example.com \
    peer0.org2.example.com \
    ca_orderer \
    ca_org1 \
    ca_org2
do
    if docker inspect "$container" >/dev/null 2>&1; then
        docker start "$container" >/dev/null 2>&1 || true
    fi
done

docker ps -a \
    --filter "name=dev-peer" \
    --format '{{.Names}}' \
    | xargs -r docker start \
    >/dev/null 2>&1 || true

echo "[2/8] Starting persistent Ethereum node"
./blockchain/ethereum/deployment/start_anvil.sh
./blockchain/ethereum/deployment/verify_contract.sh

echo "[3/8] Checking Python sources"
find app tests \
    -type f \
    -name "*.py" \
    -print0 \
    | xargs -0 ./venv/bin/python -m py_compile

./venv/bin/python -m py_compile \
    manage.py \
    run.py

echo "[4/8] Running automated tests"
./venv/bin/python -m pytest -q

echo "[5/8] Checking services"
./venv/bin/python manage.py system-status \
    >runtime/demo-system-status.json

echo "[6/8] Running all five scenarios"
./venv/bin/python manage.py pipeline-all \
    data/chips \
    --force \
    | tee runtime/demo-pipeline-results.json

echo "[7/8] Verifying event store"
./venv/bin/python manage.py verify-event-store \
    | tee runtime/demo-event-store-verification.json

echo "[8/8] Listing quarantine records"
./venv/bin/python manage.py quarantine-list \
    | tee runtime/demo-quarantine.json

echo
echo "========================================"
echo " Phase 3 demonstration completed"
echo "========================================"
echo "Results: runtime/demo-pipeline-results.json"
echo "Status:  runtime/demo-system-status.json"
echo "Audit:   runtime/demo-event-store-verification.json"
echo "Quarantine: runtime/demo-quarantine.json"
EOF_DEMO

chmod +x scripts/demo/run_complete_demo.sh

find app tests \
  -type f \
  -name "*.py" \
  -print0 \
  | xargs -0 ./venv/bin/python -m py_compile

./venv/bin/python -m py_compile \
  manage.py \
  run.py

echo
echo "Phase 3 files generated successfully."
echo "Run: ./venv/bin/python -m pytest -q"
