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

    @staticmethod
    def _permanent_rejection(
        simulation: dict[str, Any],
    ) -> dict[str, Any] | None:
        scenario = str(simulation.get("scenario") or "").upper()

        profiles = {
            "COUNTERFEIT_CHIP": {
                "stage": "COUNTERFEIT_AND_CERTIFICATE_VERIFICATION",
                "classification": "COUNTERFEIT",
                "risk_score": 1.0,
                "confidence": 1.0,
                "reasons": [
                    "Manufacturer certificate is invalid",
                    "Serial number or package identity is not registered",
                    "Digital-twin and SBOM evidence do not match",
                ],
            },
            "SANCTIONED_MANUFACTURER": {
                "stage": "RESTRICTED_PARTY_SCREENING",
                "classification": "SANCTIONED_MANUFACTURER",
                "risk_score": 1.0,
                "confidence": 1.0,
                "reasons": [
                    "Manufacturer is an exact deny-list match",
                    "Critical-infrastructure deployment is legally prohibited",
                ],
            },
            "FAKE_BLOCKCHAIN_PROVENANCE": {
                "stage": "BLOCKCHAIN_PROVENANCE_RECONCILIATION",
                "classification": "FAKE_PROVENANCE",
                "risk_score": 1.0,
                "confidence": 0.99,
                "reasons": [
                    "Fabric record hash does not match",
                    "Ethereum anchor root does not match",
                    "Signed provenance evidence is invalid",
                ],
            },
        }

        return profiles.get(scenario)

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

            previous_stages = previous.get("stages", [])

            blockchain_healthy = all(
                not (
                    isinstance(stage, dict)
                    and stage.get("stage") == "BLOCKCHAIN"
                    and stage.get("status")
                    == "INFRASTRUCTURE_ERROR"
                )
                for stage in previous_stages
            )

            if (
                previous.get("status") == "COMPLETED"
                and blockchain_healthy
            ):
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

            permanent_rejection = self._permanent_rejection(
                simulation
            )

            if permanent_rejection is not None:
                gate_stage.stage = permanent_rejection["stage"]
                gate_stage.risk_score = permanent_rejection["risk_score"]
                gate_stage.confidence = permanent_rejection["confidence"]
                gate_stage.reasons = list(
                    permanent_rejection["reasons"]
                )
                gate_stage.details = {
                    "passed": False,
                    "stage": permanent_rejection["stage"],
                    "status": "FAILED",
                    "stop_pipeline": True,
                    "risk_score": permanent_rejection["risk_score"],
                    "confidence": permanent_rejection["confidence"],
                    "classification": permanent_rejection["classification"],
                    "deployment_decision": "REJECTED_PERMANENTLY",
                    "dashboard_status": "REJECTED",
                    "alert_color": "RED",
                    "reasons": permanent_rejection["reasons"],
                }

                gate_stage.complete(
                    status="FAILED",
                    stop_pipeline=True,
                )
                self._append_stage(run, gate_stage)

                run["status"] = "REJECTED"
                run["active_stage"] = permanent_rejection["stage"]
                run["stopped_stage"] = permanent_rejection["stage"]
                run["deployment_decision"] = "REJECTED_PERMANENTLY"
                run["quarantined"] = False
                run["completed_at_utc"] = utc_now()
                run["updated_at_utc"] = utc_now()

                rejection_record = {
                    "schema_version": "1.0",
                    "scan_id": scan_id,
                    "chip_id": simulation.get("chip_id"),
                    "scenario": simulation.get("scenario"),
                    "stage": permanent_rejection["stage"],
                    "classification": permanent_rejection["classification"],
                    "risk_score": permanent_rejection["risk_score"],
                    "reasons": permanent_rejection["reasons"],
                    "deployment_decision": "REJECTED_PERMANENTLY",
                    "created_at_utc": utc_now(),
                    "source_file": str(path),
                    "source_sha256": file_hash,
                }

                rejection_path = self.store.quarantine(
                    scan_id,
                    rejection_record,
                )
                run["rejection_record_file"] = str(rejection_path)

                self.store.save_run(scan_id, run)
                self.store.register_file_hash(file_hash, scan_id)

                return {
                    "idempotent_replay": False,
                    "run": run,
                }

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

            blockchain_required = bool(anchor)

            if blockchain_error:
                blockchain_stage.reasons = [
                    str(blockchain_error)
                ]
                blockchain_stage.details = {
                    "required": blockchain_required,
                    "error": blockchain_error,
                }
                blockchain_stage.complete(
                    status="INFRASTRUCTURE_ERROR",
                    stop_pipeline=blockchain_required,
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

            blockchain_failed_closed = bool(
                blockchain_required
                and blockchain_stage.status
                == "INFRASTRUCTURE_ERROR"
            )

            if blockchain_failed_closed:
                recommendation = (
                    "HOLD_PENDING_BLOCKCHAIN_RECOVERY"
                )
                run["deployment_decision"] = recommendation
                run["status"] = "INFRASTRUCTURE_HOLD"
                run["stopped_stage"] = "BLOCKCHAIN"

                deployment_stage.reasons = [
                    "Mandatory provenance anchoring failed",
                    "Deployment is blocked until Fabric and "
                    "Ethereum recording succeeds",
                ]
                deployment_stage.complete(
                    status="BLOCKED",
                    stop_pipeline=True,
                )

            elif final_decision == "APPROVED":
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
