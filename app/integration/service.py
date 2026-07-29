"""Complete terminal-to-dashboard semiconductor security integration."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from flask import Flask

from app.integration.adapters import (
    AdapterError,
    run_ai_pipeline,
    run_hardware_pipeline,
)
from app.pipeline.simulation_gate import evaluate_simulation_gate


class IntegrationError(RuntimeError):
    """Raised when an integrated pipeline stage cannot complete safely."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def canonical_json(value: Any) -> str:
    """Return deterministic JSON suitable for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def canonical_hash(value: Any) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    """Calculate a file SHA-256 digest."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


class IntegratedPipelineService:
    """Execute every registered semiconductor security module in order."""

    STAGE_ORDER = (
        "INGESTION",
        "PUF_AUTHENTICATION",
        "HARDWARE_SECURITY",
        "AI_ANALYSIS",
        "COMPLIANCE",
        "BLOCKCHAIN",
        "DASHBOARD",
        "DEPLOYMENT_DECISION",
    )

    def __init__(
        self,
        *,
        app: Flask,
        project_root: Path,
    ) -> None:
        self.app = app
        self.project_root = project_root.resolve()
        self.run_root = (
            self.project_root
            / "data"
            / "integrated_runs"
        )
        self.run_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def run_file(
        self,
        simulation_path: Path,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Run one JSON chip through every integrated module."""
        path = simulation_path.expanduser().resolve()

        if not path.exists() or not path.is_file():
            raise IntegrationError(
                f"Simulation file does not exist: {path}"
            )

        try:
            simulation = json.loads(
                path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise IntegrationError(
                f"Invalid JSON at line {exc.lineno}, "
                f"column {exc.colno}: {path}"
            ) from exc

        if not isinstance(simulation, dict):
            raise IntegrationError(
                "Simulation JSON root must be an object"
            )

        chip_id = str(
            simulation.get("chip_id") or ""
        ).strip()

        if not chip_id:
            raise IntegrationError(
                "chip_id is required"
            )

        source_sha256 = file_hash(path)
        existing = self._find_by_source_hash(
            source_sha256
        )

        if existing and not force:
            return {
                "idempotent_replay": True,
                "run": existing,
            }

        run_id = str(uuid4())

        run: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": run_id,
            "scan_id": None,
            "chip_id": chip_id,
            "scenario": simulation.get("scenario"),
            "source_file": str(path),
            "source_sha256": source_sha256,
            "status": "RUNNING",
            "active_stage": "INGESTION",
            "stopped_stage": None,
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "completed_at_utc": None,
            "stages": [],
            "hardware": None,
            "ai": None,
            "compliance": None,
            "blockchain": None,
            "dashboard": None,
            "deployment_decision": None,
            "quarantined": False,
        }

        self._save(run)
        self._publish(
            "pipeline.started",
            run,
        )

        ingestion = self._execute_stage(
            run,
            "INGESTION",
            lambda: self._ingest(
                simulation,
                path,
                source_sha256,
            ),
            mandatory=True,
        )

        run["scan_id"] = ingestion["scan_id"]

        puf = self._execute_stage(
            run,
            "PUF_AUTHENTICATION",
            lambda: self._run_puf(simulation),
            mandatory=True,
        )

        if not puf["passed"]:
            return self._stop(
                run,
                stage="PUF_AUTHENTICATION",
                status="STOPPED",
                decision=puf[
                    "deployment_decision"
                ],
                quarantined=True,
            )

        hardware = self._execute_stage(
            run,
            "HARDWARE_SECURITY",
            lambda: self._run_hardware(
                simulation,
                ingestion["scan_id"],
                str(
                    ingestion.get("correlation_id")
                    or run["run_id"]
                ),
            ),
            mandatory=True,
        )

        run["hardware"] = hardware

        if not hardware["passed"]:
            return self._stop(
                run,
                stage="HARDWARE_SECURITY",
                status="STOPPED",
                decision=hardware[
                    "deployment_decision"
                ],
                quarantined=True,
            )

        ai = self._execute_stage(
            run,
            "AI_ANALYSIS",
            lambda: self._run_ai(
                simulation,
                hardware,
            ),
            mandatory=True,
        )

        run["ai"] = ai

        if not ai["passed"]:
            return self._stop(
                run,
                stage="AI_ANALYSIS",
                status="STOPPED",
                decision="DENIED_AND_QUARANTINED",
                quarantined=True,
            )

        compliance = self._execute_stage(
            run,
            "COMPLIANCE",
            lambda: self._run_compliance(
                simulation,
                ingestion["scan_id"],
                ai,
            ),
            mandatory=True,
        )

        run["compliance"] = compliance
        run["blockchain"] = compliance.get(
            "blockchain"
        )

        decision = str(
            compliance.get("decision", {}).get(
                "decision",
                "DENIED",
            )
        )

        blockchain_required = (
            decision == "APPROVED"
        )

        blockchain = self._execute_stage(
            run,
            "BLOCKCHAIN",
            lambda: self._verify_blockchain(
                compliance,
                required=blockchain_required,
            ),
            mandatory=blockchain_required,
        )

        run["blockchain"] = blockchain.get(
            "blockchain"
        )

        if (
            blockchain_required
            and not blockchain["passed"]
        ):
            return self._stop(
                run,
                stage="BLOCKCHAIN",
                status="INFRASTRUCTURE_HOLD",
                decision=(
                    "HOLD_PENDING_BLOCKCHAIN_RECOVERY"
                ),
                quarantined=False,
            )

        dashboard = self._execute_stage(
            run,
            "DASHBOARD",
            lambda: self._update_dashboard(run),
            mandatory=False,
        )

        run["dashboard"] = dashboard

        deployment = self._execute_stage(
            run,
            "DEPLOYMENT_DECISION",
            lambda: self._deployment_decision(
                compliance,
                hardware,
                ai,
                blockchain,
            ),
            mandatory=True,
        )

        run["deployment_decision"] = (
            deployment["decision"]
        )

        if deployment["decision"] == "DEPLOY":
            run["status"] = "COMPLETED"
        elif deployment["decision"] in {
            "DO_NOT_DEPLOY_PENDING_REVIEW",
            "LICENSE_REQUIRED",
        }:
            run["status"] = "MANUAL_REVIEW"
            run["stopped_stage"] = (
                "DEPLOYMENT_DECISION"
            )
        else:
            run["status"] = "STOPPED"
            run["stopped_stage"] = (
                "DEPLOYMENT_DECISION"
            )
            run["quarantined"] = True

        run["active_stage"] = (
            "DEPLOYMENT_DECISION"
        )
        run["completed_at_utc"] = utc_now()
        run["updated_at_utc"] = utc_now()

        self._save(run)
        self._publish(
            "pipeline.completed",
            run,
        )

        return {
            "idempotent_replay": False,
            "run": run,
        }

    def _candidate_run_files(self) -> list[Path]:
        """Return run files from both current and Phase 3 stores."""
        roots = (
            self.run_root,
            self.project_root / "data" / "pipeline_runs",
        )

        candidates: dict[Path, float] = {}

        for root in roots:
            if not root.exists():
                continue

            patterns = (
                "*.json",
                "*/run.json",
                "**/run.json",
            )

            for pattern in patterns:
                for path in root.glob(pattern):
                    if not path.is_file():
                        continue

                    try:
                        candidates[path.resolve()] = (
                            path.stat().st_mtime
                        )
                    except OSError:
                        continue

        return [
            path
            for path, _ in sorted(
                candidates.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

    @staticmethod
    def _load_run_file(
        path: Path,
    ) -> dict[str, Any] | None:
        try:
            value = json.loads(
                path.read_text(
                    encoding="utf-8",
                )
            )
        except Exception:
            return None

        if not isinstance(value, dict):
            return None

        if (
            isinstance(value.get("run"), dict)
            and not value.get("scan_id")
        ):
            value = value["run"]

        return value if isinstance(value, dict) else None

    def get_run(
        self,
        identifier: str,
    ) -> dict[str, Any]:
        """Load a run by run ID or scan ID from either run store."""
        identifier = str(identifier).strip()

        for path in self._candidate_run_files():
            run = self._load_run_file(path)

            if not run:
                continue

            if (
                str(run.get("run_id") or "") == identifier
                or str(run.get("scan_id") or "") == identifier
            ):
                return run

        raise FileNotFoundError(
            f"Integrated run not found: {identifier}"
        )

    def list_runs(
        self,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent unique runs from both supported stores."""
        runs: list[dict[str, Any]] = []
        identifiers: set[str] = set()

        for path in self._candidate_run_files():
            run = self._load_run_file(path)

            if not run:
                continue

            identifier = str(
                run.get("scan_id")
                or run.get("run_id")
                or path
            )

            if identifier in identifiers:
                continue

            identifiers.add(identifier)
            runs.append(run)

            if len(runs) >= limit:
                break

        return runs

    def _ingest(
        self,
        simulation: dict[str, Any],
        path: Path,
        source_sha256: str,
    ) -> dict[str, Any]:
        source = simulation.get("source")

        if not isinstance(source, dict):
            source = {
                "component": "terminal",
                "operator": os.getenv(
                    "USER",
                    "unknown",
                ),
            }

        submission = {
            "chip_id": simulation["chip_id"],
            "chip_file": path.name,
            "source": source,
            "evidence": {
                "simulation_file": str(path),
                "simulation_sha256": (
                    source_sha256
                ),
                "scenario": simulation.get(
                    "scenario",
                    "UNKNOWN",
                ),
            },
            "metadata": {
                key: value
                for key, value
                in simulation.items()
                if key not in {
                    "chip_id",
                    "source",
                }
            },
        }

        with self.app.test_client() as client:
            response = client.post(
                "/api/v1/scans",
                json=submission,
            )

        payload = self._response_payload(
            response,
            "scan ingestion",
        )

        return payload["data"]

    def _run_puf(
        self,
        simulation: dict[str, Any],
    ) -> dict[str, Any]:
        gate = evaluate_simulation_gate(
            simulation
        )

        if gate.stage == "PUF_AUTHENTICATION":
            return {
                "passed": gate.passed,
                "classification": (
                    gate.classification
                ),
                "risk_score": gate.risk_score,
                "confidence": gate.confidence,
                "reasons": list(gate.reasons),
                "deployment_decision": (
                    gate.deployment_decision
                ),
                "details": gate.to_dict(),
            }

        puf = (
            simulation.get(
                "hardware_security",
                {},
            ).get("puf", {})
        )

        return {
            "passed": True,
            "classification": (
                "PUF_AUTHENTICATED"
            ),
            "risk_score": 0.05,
            "confidence": float(
                puf.get(
                    "stability_score",
                    0.95,
                )
            ),
            "reasons": [],
            "deployment_decision": (
                "CONTINUE"
            ),
            "details": puf,
        }

    def _run_hardware(
        self,
        simulation: dict[str, Any],
        scan_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Execute the registered hardware service using its exact contract."""
        gate = evaluate_simulation_gate(simulation)

        if not gate.passed:
            return {
                "passed": False,
                "classification": gate.classification,
                "failed_stage": gate.stage,
                "risk_score": gate.risk_score,
                "confidence": gate.confidence,
                "reasons": list(gate.reasons),
                "deployment_decision": gate.deployment_decision,
                "details": gate.to_dict(),
            }

        service = self.app.extensions.get(
            "semisecure.hardware_pipeline"
        )

        try:
            return run_hardware_pipeline(
                service=service,
                project_root=self.project_root,
                simulation=simulation,
                scan_id=scan_id,
                chip_id=str(simulation["chip_id"]),
                correlation_id=correlation_id,
            )
        except AdapterError as exc:
            raise IntegrationError(str(exc)) from exc

    def _run_ai(
        self,
        simulation: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the registered AI service using its exact contract."""
        service = self.app.extensions.get(
            "semisecure.ai_pipeline"
        )

        try:
            return run_ai_pipeline(
                service=service,
                simulation=simulation,
                hardware_result=hardware,
            )
        except AdapterError as exc:
            raise IntegrationError(str(exc)) from exc

    def _run_compliance(
        self,
        simulation: dict[str, Any],
        scan_id: str,
        ai: dict[str, Any],
    ) -> dict[str, Any]:
        compliance = simulation.get(
            "compliance",
            {},
        )
        supplier = simulation.get(
            "supplier",
            {},
        )

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
            "defense_related": bool(
                compliance.get(
                    "defense_related",
                    False,
                )
            ),
            "specially_designed_for_military": bool(
                compliance.get(
                    "specially_designed_for_military",
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

        usml = str(
            compliance.get(
                "usml_category"
            ) or ""
        ).strip()

        if usml:
            item["usml_category"] = usml

        payload = {
            "scan_id": scan_id,
            "item": item,
            "transaction": {
                "destination_country": (
                    compliance.get(
                        "destination_country",
                        "",
                    )
                ),
                "end_use": compliance.get(
                    "end_use",
                    "",
                ),
                "end_user_type": (
                    compliance.get(
                        "end_user_type",
                        "",
                    )
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
            "ai": {
                "decision": {
                    "classification": (
                        ai["classification"]
                    ),
                    "risk_score": (
                        ai["risk_score"]
                    ),
                    "confidence_score": (
                        ai["confidence"]
                    ),
                }
            },
            "anchor_to_blockchain": True,
        }

        with self.app.test_client() as client:
            response = client.post(
                "/api/v1/compliance/evaluate",
                json=payload,
            )

        result = self._response_payload(
            response,
            "compliance evaluation",
        )

        return result["data"]

    @staticmethod
    def _verify_blockchain(
        compliance: dict[str, Any],
        *,
        required: bool,
    ) -> dict[str, Any]:
        blockchain = compliance.get(
            "blockchain"
        )
        error = compliance.get(
            "blockchain_error"
        )

        if error:
            return {
                "passed": False,
                "required": required,
                "blockchain": None,
                "error": error,
            }

        if not blockchain:
            return {
                "passed": not required,
                "required": required,
                "blockchain": None,
                "error": (
                    "Mandatory blockchain result "
                    "was not returned"
                    if required
                    else None
                ),
            }

        fabric = blockchain.get("fabric")
        ethereum = blockchain.get("ethereum")

        fabric_valid = bool(
            isinstance(fabric, dict)
            and fabric.get("committed")
            and fabric.get(
                "validation_code"
            ) == "VALID"
        )

        ethereum_valid = bool(
            isinstance(ethereum, dict)
            and ethereum.get("confirmed")
        )

        return {
            "passed": (
                fabric_valid
                and ethereum_valid
            ),
            "required": required,
            "blockchain": blockchain,
            "fabric_valid": fabric_valid,
            "ethereum_valid": ethereum_valid,
            "error": None,
        }

    def _update_dashboard(
        self,
        run: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "run_id": run["run_id"],
            "scan_id": run["scan_id"],
            "chip_id": run["chip_id"],
            "scenario": run["scenario"],
            "status": run["status"],
            "active_stage": run[
                "active_stage"
            ],
            "stopped_stage": run[
                "stopped_stage"
            ],
            "hardware": run["hardware"],
            "ai": run["ai"],
            "compliance": run["compliance"],
            "blockchain": run["blockchain"],
            "deployment_decision": run[
                "deployment_decision"
            ],
            "updated_at_utc": utc_now(),
        }

        self._publish(
            "pipeline.dashboard.updated",
            payload,
        )

        return {
            "passed": True,
            "event": (
                "pipeline.dashboard.updated"
            ),
            "published_at_utc": utc_now(),
        }

    @staticmethod
    def _deployment_decision(
        compliance: dict[str, Any],
        hardware: dict[str, Any],
        ai: dict[str, Any],
        blockchain: dict[str, Any],
    ) -> dict[str, Any]:
        if not hardware.get("passed"):
            return {
                "decision": (
                    "DENIED_AND_QUARANTINED"
                ),
                "reasons": [
                    "Hardware security failed"
                ],
            }

        if not ai.get("passed"):
            return {
                "decision": (
                    "DENIED_AND_QUARANTINED"
                ),
                "reasons": [
                    "AI security analysis failed"
                ],
            }

        decision = str(
            compliance.get(
                "decision",
                {},
            ).get(
                "decision",
                "DENIED",
            )
        )

        if decision == "APPROVED":
            if not blockchain.get("passed"):
                return {
                    "decision": (
                        "HOLD_PENDING_BLOCKCHAIN_RECOVERY"
                    ),
                    "reasons": [
                        "Mandatory provenance anchoring failed"
                    ],
                }

            return {
                "decision": "DEPLOY",
                "reasons": [
                    "Hardware, AI, compliance, "
                    "Fabric, and Ethereum passed"
                ],
            }

        if decision == "LICENSE_REQUIRED":
            return {
                "decision": (
                    "DO_NOT_DEPLOY_PENDING_REVIEW"
                ),
                "reasons": [
                    "Export licence or human approval required"
                ],
            }

        return {
            "decision": (
                "DENIED_AND_QUARANTINED"
            ),
            "reasons": [
                "Compliance policy denied deployment"
            ],
        }

    def _execute_stage(
        self,
        run: dict[str, Any],
        stage_name: str,
        function: Callable[[], Any],
        *,
        mandatory: bool,
    ) -> Any:
        started = time.perf_counter()
        started_at = utc_now()

        run["active_stage"] = stage_name
        run["updated_at_utc"] = utc_now()

        self._save(run)
        self._publish(
            "pipeline.stage.started",
            {
                "run_id": run["run_id"],
                "scan_id": run["scan_id"],
                "stage": stage_name,
                "started_at_utc": started_at,
            },
        )

        try:
            result = function()

            passed = bool(
                result.get("passed", True)
                if isinstance(result, dict)
                else True
            )

            status = (
                "PASSED"
                if passed
                else "FAILED"
            )

            stage = {
                "stage": stage_name,
                "status": status,
                "mandatory": mandatory,
                "stop_pipeline": (
                    mandatory
                    and not passed
                ),
                "started_at_utc": (
                    started_at
                ),
                "completed_at_utc": (
                    utc_now()
                ),
                "duration_ms": round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                    3,
                ),
                "result_hash": (
                    canonical_hash(result)
                ),
                "result": result,
            }

            run["stages"].append(stage)
            run["updated_at_utc"] = utc_now()
            self._save(run)

            self._publish(
                "pipeline.stage.completed",
                {
                    "run_id": run["run_id"],
                    "scan_id": run["scan_id"],
                    **stage,
                },
            )

            return result

        except Exception as exc:
            stage = {
                "stage": stage_name,
                "status": (
                    "INFRASTRUCTURE_ERROR"
                ),
                "mandatory": mandatory,
                "stop_pipeline": mandatory,
                "started_at_utc": started_at,
                "completed_at_utc": utc_now(),
                "duration_ms": round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                    3,
                ),
                "error_type": (
                    type(exc).__name__
                ),
                "error": str(exc),
            }

            run["stages"].append(stage)
            run["status"] = (
                "INFRASTRUCTURE_HOLD"
                if mandatory
                else run["status"]
            )
            run["stopped_stage"] = (
                stage_name
                if mandatory
                else run["stopped_stage"]
            )
            run["updated_at_utc"] = utc_now()

            self._save(run)
            self._publish(
                "pipeline.stage.failed",
                {
                    "run_id": run["run_id"],
                    "scan_id": run["scan_id"],
                    **stage,
                },
            )

            if mandatory:
                raise

            return {
                "passed": False,
                "error_type": (
                    type(exc).__name__
                ),
                "error": str(exc),
            }

    def _stop(
        self,
        run: dict[str, Any],
        *,
        stage: str,
        status: str,
        decision: str,
        quarantined: bool,
    ) -> dict[str, Any]:
        run["status"] = status
        run["active_stage"] = stage
        run["stopped_stage"] = stage
        run["deployment_decision"] = decision
        run["quarantined"] = quarantined
        run["completed_at_utc"] = utc_now()
        run["updated_at_utc"] = utc_now()

        self._save(run)
        self._publish(
            "pipeline.stopped",
            run,
        )

        return {
            "idempotent_replay": False,
            "run": run,
        }

    def _publish(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        publisher = self.app.extensions.get(
            "semisecure.socket_publisher"
        )

        if publisher is None:
            return

        for method_name in (
            "publish",
            "emit",
            "send",
        ):
            method = getattr(
                publisher,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                signature = inspect.signature(
                    method
                )

                if len(signature.parameters) >= 2:
                    method(
                        event_name,
                        payload,
                    )
                else:
                    method(
                        {
                            "event": event_name,
                            "data": payload,
                        }
                    )

                return
            except Exception:
                continue

    @staticmethod
    def _invoke_service(
        service: Any,
        *,
        candidates: tuple[str, ...],
        payload: dict[str, Any],
        optional: bool,
    ) -> Any:
        if service is None:
            if optional:
                return {
                    "available": False,
                    "reason": (
                        "Service extension is not registered"
                    ),
                }

            raise IntegrationError(
                "Required service is not registered"
            )

        for method_name in candidates:
            method = getattr(
                service,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                signature = inspect.signature(
                    method
                )
                parameters = list(
                    signature.parameters.values()
                )

                if not parameters:
                    return method()

                if len(parameters) == 1:
                    return method(payload)

                keyword_arguments = {
                    parameter.name: payload[
                        parameter.name
                    ]
                    for parameter in parameters
                    if parameter.name in payload
                }

                if keyword_arguments:
                    return method(
                        **keyword_arguments
                    )

                return method(payload)

            except TypeError:
                continue
            except Exception as exc:
                if optional:
                    return {
                        "available": True,
                        "method": method_name,
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error": str(exc),
                    }

                raise

        if optional:
            return {
                "available": True,
                "reason": (
                    "No supported callable service method was found"
                ),
                "service_type": (
                    type(service).__name__
                ),
            }

        raise IntegrationError(
            f"No supported method was found on "
            f"{type(service).__name__}"
        )

    @staticmethod
    def _normalise_ai_result(
        simulation: dict[str, Any],
        service_output: Any,
    ) -> dict[str, Any]:
        if isinstance(service_output, dict):
            decision = service_output.get(
                "decision",
                service_output,
            )

            if isinstance(decision, dict):
                classification = str(
                    decision.get(
                        "classification",
                        decision.get(
                            "label",
                            "",
                        ),
                    )
                    or ""
                ).upper()

                risk_score = float(
                    decision.get(
                        "risk_score",
                        decision.get(
                            "score",
                            0.0,
                        ),
                    )
                    or 0.0
                )

                confidence = float(
                    decision.get(
                        "confidence_score",
                        decision.get(
                            "confidence",
                            0.0,
                        ),
                    )
                    or 0.0
                )

                if classification:
                    return {
                        "classification": (
                            classification
                        ),
                        "risk_score": max(
                            0.0,
                            min(1.0, risk_score),
                        ),
                        "confidence": max(
                            0.0,
                            min(1.0, confidence),
                        ),
                    }

        raise IntegrationError(
            "AI pipeline did not return a usable decision containing "
            "classification, risk score, and confidence"
        )

    @staticmethod
    def _response_payload(
        response: Any,
        operation: str,
    ) -> dict[str, Any]:
        payload = response.get_json(
            silent=True
        )

        if not isinstance(payload, dict):
            raise IntegrationError(
                f"{operation} returned invalid JSON"
            )

        if (
            response.status_code >= 400
            or payload.get("ok") is False
        ):
            raise IntegrationError(
                f"{operation} failed with HTTP "
                f"{response.status_code}: "
                f"{json.dumps(payload, default=str)}"
            )

        return payload

    def _run_path(
        self,
        run_id: str,
    ) -> Path:
        return (
            self.run_root
            / run_id
            / "run.json"
        )

    def _save(
        self,
        run: dict[str, Any],
    ) -> None:
        path = self._run_path(
            str(run["run_id"])
        )
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".run.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(
                run,
                temporary,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(
                temporary.name
            )

        os.replace(
            temporary_path,
            path,
        )

    def _find_by_source_hash(
        self,
        source_sha256: str,
    ) -> dict[str, Any] | None:
        for run in self.list_runs(
            limit=10000
        ):
            if (
                run.get("source_sha256")
                == source_sha256
                and run.get("status")
                == "COMPLETED"
            ):
                blockchain = run.get(
                    "blockchain"
                )

                if blockchain:
                    return run

        return None
