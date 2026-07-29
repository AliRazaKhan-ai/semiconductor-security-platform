(() => {
    "use strict";

    const config = window.SEMISECURE_DASHBOARD || {};
    const api = new window.SemiSecure.APIClient({ apiPrefix: config.apiPrefix || "/api/v1" });
    const page = document.body.dataset.page || "dashboard";

    const state = {
        scanOrder: [],
        scans: new Map(),
        eventVersions: new Map(),
        eventsByScan: new Map(),
        notifications: [],
        notificationSignatures: new Map(),
        totalScanCount: 0,
        health: { healthy: 0, total: 0 },
        refreshing: false,
        refreshTimer: null,
        latestScanId: null,
    };

    const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
    const text = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value ?? "—"; };
    const asNumber = (value) => { const number = Number(value); return Number.isFinite(number) ? number : null; };
    const normalizeScore = window.SemiSecure.normalizeScore || ((value) => asNumber(value));
    const extractRisk = window.SemiSecure.extractRisk || (() => null);
    const extractSupplierRisk = window.SemiSecure.extractSupplierRisk || (() => null);
    const formatScore = (value) => { const score = normalizeScore(value); return score === null ? "—" : `${score.toFixed(1)}`; };
    const formatPercent = (value) => { const score = normalizeScore(value); return score === null ? "—" : `${score.toFixed(1)}%`; };
    function statusOf(scan) {
        if (!scan) return "UNKNOWN";
        const rawStatus = String(scan.status || scan.latest_payload?.status || "").toUpperCase();
        const decision = String(
            scan.deployment_decision
            || scan.compliance?.decision?.deployment_recommendation
            || scan.compliance?.decision?.decision
            || scan.latest_payload?.deployment_decision
            || ""
        ).toUpperCase();
        if (
            rawStatus === "MANUAL_REVIEW"
            || rawStatus === "LICENSE_REQUIRED"
            || decision === "LICENSE_REQUIRED"
            || decision.includes("PENDING_REVIEW")
            || decision.includes("PENDING_LICENSE")
            || decision.includes("HUMAN_REVIEW")
        ) return "MANUAL_REVIEW";
        if (scan.quarantined === true) return "QUARANTINED";
        if (["DEPLOY", "APPROVED", "APPROVED_FOR_CRITICAL_INFRASTRUCTURE", "ALLOW"].includes(decision)) return "APPROVED";
        if (decision.includes("QUARANTIN") || rawStatus === "QUARANTINED") return "QUARANTINED";
        if (decision.includes("DENIED") || decision.includes("REJECT") || decision.includes("DO_NOT_DEPLOY") || decision.includes("BLOCK")) return "REJECTED";
        if (rawStatus === "STOPPED" || rawStatus === "FAILED") return scan.quarantined ? "QUARANTINED" : "REJECTED";
        return rawStatus || "UNKNOWN";
    }

    const statusClass = (status) => {
        const value = String(status || "neutral").toLowerCase();
        if (["approved", "passed", "healthy", "ready", "alive", "committed", "confirmed"].includes(value)) return "approved";
        if (["rejected", "failed", "unhealthy", "error"].includes(value)) return "rejected";
        if (["quarantined", "processing", "degraded", "pending"].includes(value)) return "quarantined";
        if (["received", "active", "connected"].includes(value)) return "received";
        return "neutral";
    };
    const formatTime = (value) => {
        if (!value) return "—";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    };
    const relativeTime = (value) => {
        if (!value) return "now";
        const date = new Date(value); if (Number.isNaN(date.getTime())) return "now";
        const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
        return `${Math.floor(seconds / 86400)}d`;
    };
    const fragment = (value, length = 12) => { const output = String(value || "—"); return output.length > length ? `${output.slice(0, length)}…` : output; };

    function payloadCandidates(events, eventTypes = []) {
        return [...events]
            .reverse()
            .filter((event) => (
                eventTypes.includes(String(event.event_type || ""))
                || eventTypes.some((type) => (
                    String(event.event_type || "").includes(type)
                    || String(event.pipeline_stage || "").includes(type)
                ))
            ))
            .map((event) => event.payload || {});
    }

    function firstDefined(candidates) {
        for (const candidate of candidates) {
            if (
                candidate !== undefined
                && candidate !== null
                && candidate !== ""
            ) {
                return candidate;
            }
        }

        return null;
    }

    function acceptedMetadata(events) {
        const accepted = events.find(
            (event) => event.event_type === "scan.accepted"
        );

        return accepted?.payload?.metadata || {};
    }

    function stagePayload(events, tokens) {
        return [...events].reverse().find((event) => {
            const stage = String(event.pipeline_stage || "").toUpperCase();
            const type = String(event.event_type || "").toUpperCase();

            return tokens.some(
                (token) => stage.includes(token) || type.includes(token)
            );
        })?.payload || {};
    }

    function stageDetails(scan, stageName) {
        const stages = Array.isArray(scan?.stages) ? scan.stages : [];

        return stages.find(
            (stage) => String(stage.stage || "").toUpperCase() === stageName
        ) || null;
    }

    function nestedRisk(value) {
        const candidates = [
            value?.risk_score,
            value?.overall_risk,
            value?.decision?.risk_score,
            value?.compliance?.decision?.risk_score,
            value?.details?.risk_score,
        ];

        return firstDefined(candidates);
    }

    function integratedRunValue(value) {
        if (!value || typeof value !== "object") return null;

        if (
            value.run
            && typeof value.run === "object"
        ) {
            return value.run;
        }

        if (
            value.data?.run
            && typeof value.data.run === "object"
        ) {
            return value.data.run;
        }

        if (
            value.scan_id
            && Array.isArray(value.stages)
        ) {
            return value;
        }

        return null;
    }

    function syntheticEventsFromRun(run) {
        if (!run || !Array.isArray(run.stages)) return [];

        return run.stages.map((stage, index) => {
            const failed = (
                stage.status === "FAILED"
                || stage.stop_pipeline === true
            );

            return {
                event_id: `integrated-${run.scan_id}-${index + 1}`,
                event_type: failed
                    ? "stage.failed"
                    : "stage.completed",
                scan_id: run.scan_id,
                chip_id: run.chip_id,
                sequence: 100000 + index,
                timestamp_utc:
                    stage.completed_at_utc
                    || stage.started_at_utc
                    || run.updated_at_utc,
                pipeline_stage: stage.stage,
                payload: {
                    status: stage.status,
                    risk_score: stage.risk_score,
                    confidence: stage.confidence,
                    classification:
                        stage.details?.classification,
                    deployment_decision:
                        stage.details?.deployment_decision,
                    reasons: stage.reasons || [],
                    details: stage.details || {},
                },
                event_hash: "",
                synthetic: true,
            };
        });
    }

    function mergeIntegratedRun(snapshot, run) {
        if (!run) return snapshot;

        const complianceDecision =
            run.compliance?.decision || {};

        const aiDecision =
            complianceDecision.ai || {};

        const stageRisks = Array.isArray(run.stages)
            ? run.stages
                .map((stage) => Number(stage.risk_score))
                .filter(Number.isFinite)
            : [];

        const maximumStageRisk = stageRisks.length
            ? Math.max(...stageRisks)
            : null;

        const finalRisk = firstDefined([
            complianceDecision.risk_score,
            run.compliance?.supplier_risk?.risk_score,
            maximumStageRisk,
        ]);

        const finalConfidence = firstDefined([
            complianceDecision.confidence,
            aiDecision.confidence_score,
            Array.isArray(run.stages)
                ? run.stages
                    .map((stage) => Number(stage.confidence))
                    .filter(Number.isFinite)
                    .at(-1)
                : null,
        ]);

        return {
            ...snapshot,
            ...run,
            scan_id: run.scan_id || snapshot?.scan_id,
            chip_id: run.chip_id || snapshot?.chip_id,
            updated_at:
                run.updated_at_utc
                || run.completed_at_utc
                || snapshot?.updated_at,
            current_stage:
                run.stopped_stage
                || run.active_stage
                || snapshot?.current_stage,
            status: run.status || snapshot?.status,
            deployment_decision:
                run.deployment_decision
                || snapshot?.deployment_decision,
            quarantined:
                run.quarantined === true
                || snapshot?.quarantined === true,
            risk_score: finalRisk,
            confidence: finalConfidence,
            stages: run.stages || [],
            compliance: run.compliance || null,
            blockchain:
                run.blockchain
                || run.compliance?.blockchain
                || null,
            tensorflow_score: firstDefined([
                aiDecision.confidence_score,
                finalConfidence,
            ]),
            pytorch_score: firstDefined([
                aiDecision.risk_score,
                finalRisk,
            ]),
            ai_classification: firstDefined([
                aiDecision.classification,
                run.stages?.at(-1)?.details?.classification,
                run.scenario,
            ]),
            hardware_security: firstDefined([
                run.scan?.payload?.metadata?.hardware_security,
                snapshot?.latest_payload?.metadata?.hardware_security,
                snapshot?.metadata?.hardware_security,
            ]) || {},
            supplier: firstDefined([
                run.scan?.payload?.metadata?.supplier,
                run.compliance?.supplier_risk,
                snapshot?.metadata?.supplier,
            ]) || {},
            supply_chain: firstDefined([
                run.scan?.payload?.metadata?.supply_chain,
                snapshot?.metadata?.supply_chain,
            ]) || {},
        };
    }

    function deriveScan(scan, events = []) {
        const derived = { ...scan };
        const metadata = acceptedMetadata(events);

        const compliancePayload = payloadCandidates(
            events,
            ["compliance.completed", "COMPLIANCE"]
        ).at(0) || {};

        const riskPayload = payloadCandidates(
            events,
            ["risk.updated", "stage.completed", "RISK"]
        ).find((payload) => nestedRisk(payload) !== null) || {};

        const tfPayload = stagePayload(
            events,
            ["TENSORFLOW", "AI_CLASSIFIER", "TROJAN_CLASSIFIER"]
        );

        const ptPayload = stagePayload(
            events,
            ["PYTORCH", "ANOMALY", "BEHAVIOURAL"]
        );

        const fabricEvent = [...events].reverse().find(
            (event) => (
                event.event_type === "fabric.committed"
                || event.payload?.fabric?.committed === true
                || event.payload?.blockchain?.fabric?.committed === true
            )
        );

        const ethereumEvent = [...events].reverse().find(
            (event) => (
                event.event_type === "ethereum.anchor_confirmed"
                || event.payload?.ethereum?.confirmed === true
                || event.payload?.blockchain?.ethereum?.confirmed === true
            )
        );

        const compliance = firstDefined([
            scan.compliance,
            compliancePayload.compliance,
            compliancePayload,
        ]) || null;

        const blockchain = firstDefined([
            scan.blockchain,
            compliance?.blockchain,
            compliancePayload.blockchain,
        ]) || null;

        const complianceDecision = compliance?.decision || {};
        const supplierRisk = firstDefined([
            scan.supplier_risk,
            compliance?.supplier_risk,
            complianceDecision.supplier_risk,
            metadata.supplier,
        ]);

        derived.metadata = metadata;
        derived.hardware_security = firstDefined([
            scan.hardware_security,
            metadata.hardware_security,
        ]) || {};

        derived.manufacturing = firstDefined([
            scan.manufacturing,
            metadata.manufacturing,
        ]) || {};

        derived.supplier = firstDefined([
            scan.supplier,
            metadata.supplier,
        ]) || {};

        derived.supply_chain = firstDefined([
            scan.supply_chain,
            metadata.supply_chain,
        ]) || {};

        derived.compliance = compliance;
        derived.blockchain = blockchain;

        derived.deployment_decision = firstDefined([
            scan.deployment_decision,
            complianceDecision.deployment_recommendation,
            complianceDecision.decision,
            metadata.expected_results?.deployment_decision,
        ]);

        derived.quarantined = Boolean(
            scan.quarantined
            || String(derived.deployment_decision || "")
                .toUpperCase()
                .includes("QUARANTIN")
        );

        derived.risk_score = firstDefined([
            extractRisk(scan),
            nestedRisk(riskPayload),
            complianceDecision.risk_score,
            compliance?.supplier_risk?.risk_score,
            scan.stages?.reduce(
                (maximum, stage) => Math.max(
                    maximum,
                    Number(stage.risk_score || 0)
                ),
                0
            ),
        ]);

        derived.supplier_risk = firstDefined([
            extractSupplierRisk(scan),
            supplierRisk?.risk_score,
            supplierRisk?.country_risk,
            metadata.supplier?.country_risk,
        ]);

        const aiDecision = complianceDecision.ai || {};

        derived.tensorflow_score = firstDefined([
            scan.tensorflow_score,
            tfPayload.confidence,
            tfPayload.probability,
            tfPayload.trojan_probability,
            tfPayload.score,
            aiDecision.confidence_score,
        ]);

        derived.pytorch_score = firstDefined([
            scan.pytorch_score,
            ptPayload.anomaly_score,
            ptPayload.reconstruction_error,
            ptPayload.score,
            aiDecision.risk_score,
        ]);

        derived.ai_classification = firstDefined([
            scan.ai_classification,
            aiDecision.classification,
            complianceDecision.classification,
        ]);

        derived.fabric_tx = firstDefined([
            scan.fabric_tx,
            blockchain?.fabric?.transaction_id,
            compliance?.blockchain?.fabric?.transaction_id,
            fabricEvent?.payload?.transaction_id,
            fabricEvent?.payload?.fabric?.transaction_id,
        ]);

        derived.fabric_committed = Boolean(firstDefined([
            scan.fabric_committed,
            blockchain?.fabric?.committed,
            compliance?.blockchain?.fabric?.committed,
            fabricEvent?.payload?.committed,
            fabricEvent?.payload?.fabric?.committed,
        ]));

        derived.fabric_validation = firstDefined([
            scan.fabric_validation,
            blockchain?.fabric?.validation_code,
            compliance?.blockchain?.fabric?.validation_code,
        ]);

        derived.ethereum_tx = firstDefined([
            scan.ethereum_tx,
            blockchain?.ethereum?.transaction_hash,
            compliance?.blockchain?.ethereum?.transaction_hash,
            ethereumEvent?.payload?.transaction_hash,
            ethereumEvent?.payload?.ethereum?.transaction_hash,
        ]);

        derived.ethereum_confirmed = Boolean(firstDefined([
            scan.ethereum_confirmed,
            blockchain?.ethereum?.confirmed,
            compliance?.blockchain?.ethereum?.confirmed,
            ethereumEvent?.payload?.confirmed,
            ethereumEvent?.payload?.ethereum?.confirmed,
        ]));

        derived.status = statusOf(derived);

        return derived;
    }

    function mergeSocketEvent(event) {
        if (!event || !event.scan_id) return;
        const events = state.eventsByScan.get(event.scan_id) || [];
        if (!events.some((item) => item.event_id === event.event_id)) events.push(event);
        events.sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0));
        state.eventsByScan.set(event.scan_id, events);
        state.eventVersions.set(event.scan_id, Number(event.sequence || events.length));

        const existing = state.scans.get(event.scan_id) || { scan_id: event.scan_id, chip_id: event.chip_id };
        const payloadStatus = event.payload?.status;
        const eventStatus = event.event_type === "deployment.approved" ? "APPROVED" : event.event_type === "deployment.rejected" ? "REJECTED" : event.event_type === "chip.quarantined" ? "QUARANTINED" : event.event_type === "stage.failed" ? "FAILED" : null;
        const merged = deriveScan({
            ...existing,
            chip_id: event.chip_id || existing.chip_id,
            updated_at: event.timestamp_utc,
            current_stage: event.pipeline_stage,
            last_event_type: event.event_type,
            last_event_hash: event.event_hash,
            last_sequence: event.sequence,
            status: eventStatus || payloadStatus || existing.status || "PROCESSING",
            latest_payload: event.payload || {},
        }, events);
        state.scans.set(event.scan_id, merged);
        state.scanOrder = [event.scan_id, ...state.scanOrder.filter((id) => id !== event.scan_id)];
        state.latestScanId = event.scan_id;
        addNotification(event, true);
        renderDashboard();
    }

    async function hydrateScan(meta) {
        const cached = state.scans.get(meta.scan_id);

        const currentSequence =
            state.eventVersions.get(meta.scan_id) || 0;

        const [
            snapshotResult,
            eventsResult,
            integratedRunResult,
        ] = await Promise.allSettled([
            api.scan(meta.scan_id),
            api.scanEvents(
                meta.scan_id,
                {
                    afterSequence: currentSequence,
                    limit: 1000,
                }
            ),
            api.integrationRun(meta.scan_id),
        ]);

        const snapshot = snapshotResult.status === "fulfilled"
            ? snapshotResult.value
            : { ...cached, ...meta };

        const run = integratedRunResult.status === "fulfilled"
            ? integratedRunValue(integratedRunResult.value)
            : null;

        const mergedSnapshot = mergeIntegratedRun(
            { ...meta, ...snapshot },
            run
        );

        const currentEvents =
            state.eventsByScan.get(meta.scan_id) || [];

        const fetchedEvents =
            eventsResult.status === "fulfilled"
                && Array.isArray(eventsResult.value)
                ? eventsResult.value
                : [];

        const syntheticEvents = syntheticEventsFromRun(run);

        const known = new Set(
            currentEvents.map((event) => event.event_id)
        );

        [...fetchedEvents, ...syntheticEvents].forEach(
            (event) => {
                if (!known.has(event.event_id)) {
                    currentEvents.push(event);
                    known.add(event.event_id);
                }
            }
        );

        currentEvents.sort(
            (a, b) => Number(a.sequence || 0)
                - Number(b.sequence || 0)
        );

        state.eventsByScan.set(
            meta.scan_id,
            currentEvents
        );

        state.eventVersions.set(
            meta.scan_id,
            Number(
                fetchedEvents.at(-1)?.sequence
                || snapshot.last_sequence
                || currentSequence
            )
        );

        state.scans.set(
            meta.scan_id,
            deriveScan(
                mergedSnapshot,
                currentEvents
            )
        );
    }

    async function refreshScans({ force = false } = {}) {
        if (state.refreshing && !force) return;
        state.refreshing = true;
        const refreshButton = document.getElementById("manualRefreshButton");
        if (refreshButton) refreshButton.disabled = true;
        try {
            const latest = await api.latestScans(50);
            const list = Array.isArray(latest) ? latest : [];
            state.scanOrder = list.map((item) => item.scan_id);
            list.forEach((item) => { if (!state.scans.has(item.scan_id)) state.scans.set(item.scan_id, item); });
            await Promise.allSettled(
                list.slice(0, 24).map(hydrateScan)
            );
            state.latestScanId = state.scanOrder[0] || null;
            syncRestNotifications(orderedScans());
            renderDashboard();
            updateRefreshStamp();
            setConnection(
                "connected",
                "Backend connected; REST refresh active"
            );
        } catch (error) {
            addLocalNotification("Backend refresh failed", error.message, "danger");
            setConnection("error", "Backend unavailable");
        } finally {
            state.refreshing = false;
            if (refreshButton) refreshButton.disabled = false;
        }
    }

    function orderedScans() {
        return state.scanOrder.map((scanId) => state.scans.get(scanId)).filter(Boolean);
    }

    function renderDashboard() {
        if (page !== "dashboard") return;
        const scans = orderedScans();
        renderKPIs(scans);
        renderScanTable(scans);
        if (window.dashboardCharts) window.dashboardCharts.update(scans);
        const latest = scans[0];
        const events = latest ? state.eventsByScan.get(latest.scan_id) || [] : [];
        if (window.pipelineTimeline) latest ? window.pipelineTimeline.update(latest, events) : window.pipelineTimeline.reset();
        renderAI(latest, events);
        renderHardware(latest, events);
        renderCompliance(latest, events);
        renderInfrastructure(latest);
        if (window.provenanceController) window.provenanceController.updatePanel(scans, state.eventsByScan);
    }

    function renderKPIs(scans) {
        const statuses = scans.map(statusOf);

        const risks = scans
            .map((scan) => extractRisk(scan))
            .filter((value) => value !== null);

        const averageRisk = risks.length
            ? risks.reduce((sum, value) => sum + value, 0) / risks.length
            : 0;

        const highRisk = scans.filter((scan) => {
            const risk = extractRisk(scan);
            const status = statusOf(scan);

            return (
                risk !== null
                && risk >= 70
                && status !== "APPROVED"
            );
        }).length;

        const fabricCommits = scans.filter(
            (scan) => (
                scan.fabric_committed === true
                || scan.blockchain?.fabric?.committed === true
                || scan.compliance?.blockchain?.fabric?.committed === true
            )
        ).length;

        text("kpiTotalScans", state.totalScanCount || scans.length);

        text(
            "kpiApproved",
            statuses.filter((status) => status === "APPROVED").length
        );

        text(
            "kpiRejected",
            statuses.filter((status) => status === "REJECTED").length
        );

        text(
            "kpiQuarantined",
            statuses.filter((status) => status === "QUARANTINED").length
        );

        text(
            "kpiManualReview",
            statuses.filter((status) => status === "MANUAL_REVIEW").length
        );

        text("kpiAverageRisk", averageRisk.toFixed(1));
        text("kpiHighRisk", highRisk);
        text("kpiFabricCommits", fabricCommits);

        text(
            "kpiHealthyServices",
            `${state.health.healthy}/${state.health.total}`
        );
    }

    function renderScanTable(scans) {
        const body = document.getElementById("liveScanTableBody");
        if (!body) return;
        text("scanTableCount", `${scans.length} records`);
        if (!scans.length) {
            body.innerHTML = '<tr><td colspan="8"><div class="empty-state"><span>⌁</span><p>Waiting for terminal-originated scan events</p></div></td></tr>';
            return;
        }
        body.innerHTML = scans.slice(0, 25).map((scan) => {
            const risk = extractRisk(scan);
            const status = statusOf(scan);
            const scanId = encodeURIComponent(scan.scan_id);
            return `<tr>
                <td title="${escapeHTML(scan.updated_at || "")}">${escapeHTML(formatTime(scan.updated_at))}</td>
                <td><a class="table-link" href="/dashboard/chips/${encodeURIComponent(scan.chip_id || "unknown")}">${escapeHTML(scan.chip_id || "—")}</a></td>
                <td><span class="mono" title="${escapeHTML(scan.scan_id)}">${escapeHTML(fragment(scan.scan_id, 13))}</span></td>
                <td>${escapeHTML(scan.current_stage || "INGESTION")}</td>
                <td><strong style="color:${risk !== null && risk >= 70 ? "var(--red)" : risk !== null && risk >= 40 ? "var(--amber)" : "var(--green)"}">${risk === null ? "—" : risk.toFixed(1)}</strong></td>
                <td><span class="status-badge ${statusClass(status)}">${escapeHTML(status)}</span></td>
                <td><span class="hash-fragment" title="${escapeHTML(scan.last_event_hash || "")}">${escapeHTML(fragment(scan.last_event_hash, 14))}</span></td>
                <td class="text-end"><a class="table-link" href="/dashboard/scans/${scanId}">Open →</a></td>
            </tr>`;
        }).join("");
    }

    function stageResult(events, stageTokens) {
        const event = [...events].reverse().find((item) => stageTokens.some((token) => String(item.pipeline_stage || "").toUpperCase().includes(token)));
        if (!event) return { state: "waiting", label: "Waiting" };
        const type = String(event.event_type || "").toLowerCase();
        const failed = type.includes("failed") || type.includes("rejected") || String(event.payload?.status || "").toUpperCase() === "FAILED";
        return { state: failed ? "failed" : type.includes("started") ? "active" : "passed", label: failed ? "Failed" : type.includes("started") ? "Active" : "Passed", event };
    }

    function renderHardware(scan, events) {
        const hardware = scan?.hardware_security || {};
        const puf = hardware.puf || {};
        const opentitan = hardware.opentitan || {};
        const chipwhisperer = hardware.chipwhisperer || {};
        const yosys = hardware.yosys || {};
        const verilator = hardware.verilator || {};

        const pufPassed = (
            puf.authentication_expected === true
            && Number(puf.stability_score || 0) >= 0.80
        );

        const opentitanPassed = (
            opentitan.secure_boot === true
            && opentitan.debug_locked === true
            && opentitan.otp_integrity === true
            && opentitan.rom_digest_valid === true
        );

        const chipwhispererFailed = (
            Number(chipwhisperer.power_rms || 0) > 1.5
            || Number(chipwhisperer.em_rms || 0) > 1.5
            || Number(chipwhisperer.timing_jitter || 0) > 0.5
        );

        const edaPassed = (
            verilator.simulation_passed === true
            && Number(yosys.netlist_delta_ratio || 0) < 0.10
            && Number(yosys.rare_net_ratio || 0) < 0.15
        );

        const metadataAvailable = Object.keys(hardware).length > 0;

        const results = [
            {
                code: "PUF",
                description: "Chip authentication",
                state: !metadataAvailable
                    ? "waiting"
                    : pufPassed ? "passed" : "failed",
                label: !metadataAvailable
                    ? "Waiting"
                    : pufPassed ? "Verified" : "Failed",
            },
            {
                code: "OT",
                description: "OpenTitan attestation",
                state: !metadataAvailable
                    ? "waiting"
                    : opentitanPassed ? "passed" : "failed",
                label: !metadataAvailable
                    ? "Waiting"
                    : opentitanPassed ? "Verified" : "Failed",
            },
            {
                code: "CW",
                description: "Side-channel analysis",
                state: !metadataAvailable
                    ? "waiting"
                    : chipwhispererFailed ? "failed" : "passed",
                label: !metadataAvailable
                    ? "Waiting"
                    : chipwhispererFailed ? "Anomaly" : "Clear",
            },
            {
                code: "EDA",
                description: "Yosys + Verilator",
                state: !metadataAvailable
                    ? "waiting"
                    : edaPassed ? "passed" : "failed",
                label: !metadataAvailable
                    ? "Waiting"
                    : edaPassed ? "Verified" : "Failed",
            },
        ];

        const container = document.getElementById("hardwareModules");

        if (!container) return;

        container.innerHTML = results.map((result) => `
            <div class="security-module ${result.state}">
                <span>${result.code}</span>
                <strong>${result.label}</strong>
                <small>${result.description}</small>
            </div>
        `).join("");

        const failed = results.some(
            (result) => result.state === "failed"
        );

        const verified = results.every(
            (result) => result.state === "passed"
        );

        setBadge(
            "hardwareOverall",
            failed
                ? "SECURITY FINDING"
                : verified
                    ? "VERIFIED"
                    : scan
                        ? "EVIDENCE LOADED"
                        : "WAITING",
            failed
                ? "rejected"
                : verified
                    ? "approved"
                    : scan
                        ? "received"
                        : "neutral"
        );
    }

    function renderAI(scan, events) {
        const risk = extractRisk(scan);

        const finalStage = Array.isArray(scan?.stages)
            ? scan.stages.at(-1)
            : null;

        const stageConfidence = firstDefined([
            finalStage?.confidence,
            finalStage?.details?.confidence,
            scan?.confidence,
        ]);

        const tf = firstDefined([
            scan?.tensorflow_score,
            scan?.compliance?.decision?.ai
                ?.confidence_score,
            stageConfidence,
        ]);

        const pt = firstDefined([
            scan?.pytorch_score,
            scan?.compliance?.decision?.ai
                ?.risk_score,
            risk === null ? null : risk / 100,
        ]);

        const classification = String(firstDefined([
            scan?.ai_classification,
            scan?.compliance?.decision?.ai
                ?.classification,
            finalStage?.details?.classification,
            scan?.scenario,
        ]) || "UNKNOWN").toUpperCase();

        text(
            "tensorflowValue",
            tf === null
                ? "—"
                : formatPercent(tf)
        );

        text(
            "pytorchValue",
            pt === null
                ? "—"
                : formatPercent(pt)
        );

        text(
            "riskFusionValue",
            risk === null
                ? "—"
                : risk.toFixed(1)
        );

        text(
            "modelIntegrityValue",
            scan
                ? "Verified"
                : "Waiting"
        );

        const failed = (
            classification.includes("TROJAN")
            || classification.includes("TAMPER")
            || classification.includes("WEAK")
            || (risk !== null && risk >= 70)
        );

        const complete = (
            scan
            && risk !== null
        );

        setBadge(
            "aiOverall",
            failed
                ? "HIGH-RISK FINDING"
                : complete
                    ? "ANALYSIS COMPLETE"
                    : scan
                        ? "ANALYSING"
                        : "WAITING",
            failed
                ? "rejected"
                : complete
                    ? "approved"
                    : scan
                        ? "processing"
                        : "neutral"
        );
    }

    function renderCompliance(scan, events) {
        const compliance = scan?.compliance || {};
        const decision = (
            compliance.decision
            && typeof compliance.decision === "object"
        )
            ? compliance.decision
            : {};

        const exportControl =
            compliance.export_control
            || decision.export_control
            || {};

        const decisionText = String(
            decision.decision
            || compliance.status
            || ""
        ).toUpperCase();

        const pipelineStoppedBeforeCompliance = (
            scan
            && !scan.compliance
            && scan.status === "STOPPED"
        );

        const passed = [
            "APPROVED",
            "PASSED",
            "COMPLIANT",
        ].includes(decisionText);

        const failed = (
            decisionText.includes("DENIED")
            || decisionText.includes("REJECT")
            || decisionText.includes("FAILED")
        );

        const confidence = firstDefined([
            decision.confidence,
            exportControl.confidence,
            scan?.confidence,
        ]);

        const normalized = normalizeScore(confidence);

        text(
            "complianceScore",
            normalized === null
                ? pipelineStoppedBeforeCompliance
                    ? "Not executed"
                    : "—"
                : `${normalized.toFixed(1)}%`
        );

        const meter = document.getElementById(
            "complianceMeter"
        );

        if (meter) {
            meter.style.width = `${
                normalized === null ? 0 : normalized
            }%`;
        }

        setBadge(
            "complianceOverall",
            passed
                ? "APPROVED"
                : failed
                    ? "FAILED"
                    : pipelineStoppedBeforeCompliance
                        ? "STOPPED BEFORE COMPLIANCE"
                        : Object.keys(compliance).length
                            ? "REVIEWED"
                            : "WAITING",
            passed
                ? "approved"
                : failed
                    ? "rejected"
                    : pipelineStoppedBeforeCompliance
                        ? "quarantined"
                        : Object.keys(compliance).length
                            ? "received"
                            : "neutral"
        );

        const metadataCompliance =
            scan?.scan?.payload?.metadata?.compliance
            || scan?.metadata?.compliance
            || {};

        const itarStatus = firstDefined([
            exportControl.itar?.status,
            exportControl.itar_status,
            metadataCompliance.defense_related === false
                ? "NOT_INDICATED"
                : null,
        ]);

        const earStatus = firstDefined([
            exportControl.ear?.status,
            exportControl.classification,
            metadataCompliance.eccn,
        ]);

        const endUseStatus = firstDefined([
            exportControl.decision,
            metadataCompliance.end_use
                ? "DECLARED"
                : null,
        ]);

        const dualUseStatus = firstDefined([
            exportControl.license_status,
            exportControl.jurisdiction,
            metadataCompliance.subject_to_ear === true
                ? "EAR REVIEW REQUIRED"
                : null,
        ]);

        const notExecutedLabel =
            pipelineStoppedBeforeCompliance
                ? "NOT EXECUTED"
                : "NOT AVAILABLE";

        const checks = [
            [
                "ITAR screening",
                itarStatus || notExecutedLabel,
            ],
            [
                "EAR classification",
                earStatus || notExecutedLabel,
            ],
            [
                "End-use validation",
                endUseStatus || notExecutedLabel,
            ],
            [
                "Dual-use controls",
                dualUseStatus || notExecutedLabel,
            ],
        ];

        const list = document.getElementById(
            "complianceChecklist"
        );

        if (!list) return;

        list.innerHTML = checks.map(([label, result]) => {
            const resultText = String(result);
            const upper = resultText.toUpperCase();

            const resultFailed = (
                upper.includes("DENIED")
                || upper.includes("FAIL")
                || upper.includes("BLOCKED")
            );

            const resultPending = (
                upper.includes("NOT EXECUTED")
                || upper.includes("NOT AVAILABLE")
                || upper.includes("PENDING")
            );

            const resultPassed = (
                !resultFailed
                && !resultPending
            );

            return `
                <div>
                    <span class="check-icon ${
                        resultPassed
                            ? "passed"
                            : resultFailed
                                ? "failed"
                                : "neutral"
                    }">${
                        resultPassed
                            ? "✓"
                            : resultFailed
                                ? "×"
                                : "•"
                    }</span>
                    <span>${label}</span>
                    <strong>${escapeHTML(resultText)}</strong>
                </div>
            `;
        }).join("");
    }

    function renderInfrastructure(scan) {
        const status = statusOf(scan);
        document.querySelectorAll("[data-infrastructure]").forEach((card) => {
            const badge = card.querySelector(".mini-state");
            card.classList.remove("approved", "rejected");
            if (status === "APPROVED") {
                card.classList.add("approved");
                badge.textContent = "APPROVED";
                badge.className = "mini-state healthy";
                return;
            }
            if (status === "MANUAL_REVIEW") {
                badge.textContent = "LICENCE / REVIEW HOLD";
                badge.className = "mini-state warning";
                return;
            }
            if (["REJECTED", "FAILED", "QUARANTINED"].includes(status)) {
                card.classList.add("rejected");
                badge.textContent = "BLOCKED";
                badge.className = "mini-state failed";
                return;
            }
            badge.textContent = scan ? "PENDING" : "NO DECISION";
            badge.className = "mini-state neutral";
        });
    }

    function setBadge(id, label, css) { const node = document.getElementById(id); if (node) { node.textContent = label; node.className = `status-badge ${css}`; } }

    function notificationMetadata(event) {
        const type = String(event.event_type || "platform.event");
        if (type.includes("failed") || type.includes("rejected") || type.includes("quarantined")) return { severity: "danger", glyph: "!", title: type.replaceAll(".", " ") };
        if (type.includes("risk") || type.includes("compliance")) return { severity: "warning", glyph: "R", title: type.replaceAll(".", " ") };
        if (type.includes("approved") || type.includes("completed") || type.includes("committed") || type.includes("confirmed")) return { severity: "success", glyph: "✓", title: type.replaceAll(".", " ") };
        return { severity: "info", glyph: "⌁", title: type.replaceAll(".", " ") };
    }

    function addNotification(event, toast = false) {
        const meta = notificationMetadata(event);
        const message = firstDefined([event.payload?.message, event.payload?.reason, event.payload?.status, `${event.pipeline_stage || "Platform"} event for ${event.chip_id || "a chip"}`]);
        state.notifications.unshift({ id: event.event_id || `${Date.now()}-${Math.random()}`, severity: meta.severity, glyph: meta.glyph, title: meta.title, message, timestamp: event.timestamp_utc || new Date().toISOString() });
        state.notifications = state.notifications.slice(0, 60);
        renderNotifications();
        if (toast && ["danger", "warning"].includes(meta.severity)) showToast(meta.title, message, meta.severity);
    }

    function addLocalNotification(title, message, severity = "info") {
        state.notifications.unshift({ id: `${Date.now()}-${Math.random()}`, severity, glyph: severity === "danger" ? "!" : severity === "warning" ? "R" : "⌁", title, message, timestamp: new Date().toISOString() });
        state.notifications = state.notifications.slice(0, 60); renderNotifications();
    }

    function notificationSeverityForStatus(status) {
        if (status === "REJECTED") return "danger";
        if (status === "QUARANTINED") return "danger";
        if (status === "MANUAL_REVIEW") return "warning";
        if (status === "APPROVED") return "success";
        return "info";
    }

    function syncRestNotifications(scans) {
        scans.forEach((scan) => {
            if (!scan?.scan_id) return;

            const status = statusOf(scan);
            const stage = String(
                scan.stopped_stage
                || scan.current_stage
                || scan.active_stage
                || "INGESTION"
            );
            const decision = String(
                scan.deployment_decision
                || status
            );
            const signature = [
                status,
                stage,
                decision,
                scan.updated_at
                    || scan.updated_at_utc
                    || scan.completed_at_utc
                    || "",
            ].join("|");

            if (
                state.notificationSignatures.get(scan.scan_id)
                === signature
            ) {
                return;
            }

            state.notificationSignatures.set(
                scan.scan_id,
                signature
            );

            const severity =
                notificationSeverityForStatus(status);

            const title = status === "APPROVED"
                ? "Chip approved"
                : status === "REJECTED"
                    ? "Chip permanently rejected"
                    : status === "QUARANTINED"
                        ? "Chip quarantined"
                        : status === "MANUAL_REVIEW"
                            ? "Manual review required"
                            : "Scan state updated";

            const risk = extractRisk(scan);
            const riskText = risk === null
                ? ""
                : ` Risk ${risk.toFixed(1)}.`;

            state.notifications.unshift({
                id: `rest-${scan.scan_id}-${signature}`,
                severity,
                glyph: severity === "danger"
                    ? "!"
                    : severity === "warning"
                        ? "R"
                        : severity === "success"
                            ? "✓"
                            : "⌁",
                title,
                message:
                    `${scan.chip_id || "Unknown chip"} — `
                    + `${stage.replaceAll("_", " ")}. `
                    + `${decision.replaceAll("_", " ")}.`
                    + riskText,
                timestamp:
                    scan.updated_at
                    || scan.updated_at_utc
                    || scan.completed_at_utc
                    || new Date().toISOString(),
            });
        });

        state.notifications = state.notifications
            .slice(0, 60);
        renderNotifications();
    }

    function renderNotifications() {
        const markup = state.notifications.length ? state.notifications.map((item) => `<article class="notification-item ${item.severity}"><div class="notification-glyph">${escapeHTML(item.glyph)}</div><div class="notification-copy"><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(item.message)}</span></div><time class="notification-time" datetime="${escapeHTML(item.timestamp)}">${escapeHTML(relativeTime(item.timestamp))}</time></article>`).join("") : '<div class="empty-state compact"><span>⌁</span><p>No scan events have been recorded</p></div>';
        const panel = document.getElementById("notificationPanelList"); if (panel) panel.innerHTML = markup;
        const drawer = document.getElementById("notificationDrawerList"); if (drawer) drawer.innerHTML = markup;
        text("notificationCount", Math.min(99, state.notifications.length));
    }

    function showToast(title, message, severity) {
        const container = document.getElementById("toastContainer"); if (!container || !window.bootstrap?.Toast) return;
        const toast = document.createElement("div");
        toast.className = "toast cyber-toast"; toast.setAttribute("role", "alert"); toast.setAttribute("aria-live", "assertive"); toast.setAttribute("aria-atomic", "true");
        toast.innerHTML = `<div class="toast-header"><span class="notification-glyph me-2">${severity === "danger" ? "!" : "R"}</span><strong class="me-auto">${escapeHTML(title)}</strong><small>now</small><button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button></div><div class="toast-body">${escapeHTML(message)}</div>`;
        container.appendChild(toast); const instance = new window.bootstrap.Toast(toast, { delay: 6500 }); toast.addEventListener("hidden.bs.toast", () => toast.remove()); instance.show();
    }

    function setConnection(connectionState, message) {
        const pill = document.getElementById("connectionPill"); if (pill) pill.dataset.state = connectionState;
        text(
            "connectionText",
            connectionState === "connected"
                ? "Backend connected"
                : connectionState === "connecting"
                    ? "Connecting"
                    : connectionState === "unavailable"
                        ? "REST monitoring"
                        : connectionState === "error"
                            ? "REST monitoring"
                            : "Reconnecting"
        );
        // Socket transport is optional. REST remains the authoritative fallback.
        if (page === "system-health") text("healthSocket", connectionState.toUpperCase());
    }

    function updateClock() { const date = new Date(); text("utcClock", `${date.toISOString().slice(11, 19)} UTC`); }
    function updateRefreshStamp() { text("lastRefresh", `Last refreshed ${new Date().toLocaleTimeString()}`); }

    async function initializeMainDashboard() {
        window.dashboardCharts = new window.SemiSecure.DashboardCharts(); window.dashboardCharts.initialize();
        window.pipelineTimeline = new window.SemiSecure.PipelineTimeline(document.getElementById("pipelineTrack"), { statusNode: document.getElementById("pipelineStatus"), messageNode: document.getElementById("pipelineMessage"), chipNode: document.getElementById("pipelineChip") });
        window.provenanceController = new window.SemiSecure.ProvenanceController(api);
        window.healthController = new window.SemiSecure.ServiceHealthController(api, {
            compactContainer: document.getElementById("serviceHealthList"),
            onSummary: ({ healthy, total, system }) => { state.health = { healthy, total }; state.totalScanCount = system?.event_store?.scan_count || state.totalScanCount; renderKPIs(orderedScans()); },
        });
        document.getElementById("manualRefreshButton")?.addEventListener("click", () => refreshScans({ force: true }));
        document.getElementById("clearNotificationsButton")?.addEventListener("click", () => { state.notifications = []; renderNotifications(); });
        (config.initialScans || []).forEach((scan) => { state.scans.set(scan.scan_id, scan); state.scanOrder.push(scan.scan_id); });
        renderDashboard(); renderNotifications();
        await Promise.allSettled([refreshScans({ force: true }), window.healthController.refresh()]);
        state.refreshTimer = window.setInterval(() => { refreshScans(); window.healthController.refresh(); }, Math.max(3000, Number(config.refreshIntervalMs) || 5000));
    }

    function renderScanDetailSummary(scan) {
        const status = statusOf(scan);
        const risk = extractRisk(scan);
        const manufacturing = scan?.manufacturing || {};
        const supplier = scan?.supplier || {};
        const supplyChain = scan?.supply_chain || {};
        text("scanDetailStatus", status);
        text("scanDetailStage", scan?.stopped_stage || scan?.current_stage || scan?.active_stage || "INGESTION");
        text("scanDetailRisk", risk === null ? "—" : risk.toFixed(1));
        text("scanDetailUpdated", formatTime(scan?.updated_at || scan?.completed_at_utc));
        text("manufacturingCountry", manufacturing.country_of_origin);
        text("manufacturingDesignHouse", manufacturing.design_house);
        text("manufacturingFabrication", manufacturing.fabrication_facility);
        text("manufacturingPackaging", manufacturing.packaging_facility);
        text("manufacturingTest", manufacturing.test_facility);
        text("manufacturingDistributor", manufacturing.distributor || "Direct controlled custody");
        text("manufacturingLot", manufacturing.lot_id);
        text("manufacturingWafer", manufacturing.wafer_id);
        text("manufacturingSerial", manufacturing.serial_number);
        text("manufacturingStage", manufacturing.current_stage);
        text("supplierName", supplier.name);
        text("supplierId", supplier.supplier_id);
        text("supplierCountry", supplier.country);
        const custody = manufacturing.chain_of_custody_complete;
        text("chainOfCustody", custody === true ? "COMPLETE" : custody === false ? "INCOMPLETE" : "UNKNOWN");
        text("digitalTwinStatus", supplyChain.digital_twin_match === true ? "MATCHED" : supplyChain.digital_twin_match === false ? "MISMATCH" : "NOT RECORDED");
        text("sbomStatus", supplyChain.sbom_match === true ? "MATCHED" : supplyChain.sbom_match === false ? "MISMATCH" : "NOT RECORDED");
        setBadge("custodyStatus", custody === true ? "CUSTODY VERIFIED" : custody === false ? "CUSTODY FAILURE" : "NO CUSTODY RESULT", custody === true ? "approved" : custody === false ? "rejected" : "neutral");
        text("deploymentDecision", scan?.deployment_decision);
        text("scanScenario", scan?.scenario);
        text("scanStoppedStage", scan?.stopped_stage || "NONE");
        text("scanAIClassification", scan?.ai_classification);
        text("scanComplianceConfidence", scan?.confidence === null || scan?.confidence === undefined ? "NOT EXECUTED" : formatPercent(scan.confidence));
        text("scanFabricValidation", scan?.fabric_validation || (scan?.fabric_committed ? "VALID" : "NOT COMMITTED"));
        text("scanEthereumConfirmation", scan?.ethereum_confirmed === true ? "CONFIRMED" : "NOT ANCHORED");
        text("scanCorrelationId", scan?.correlation_id);
        text("scanLastEvent", scan?.last_event_type);
        text("scanEventHash", scan?.last_event_hash);
        const payload = document.getElementById("scanPayload");
        if (payload) payload.textContent = JSON.stringify(scan, null, 2);
    }

    async function initializeScanDetail() {
        const root = document.getElementById("scanDetailPipeline"); if (!root) return;
        const scanId = root.dataset.scanId; if (!scanId) return;
        const timeline = new window.SemiSecure.PipelineTimeline(document.getElementById("pipelineTrack"), { statusNode: document.getElementById("pipelineStatus"), messageNode: document.getElementById("pipelineMessage") });
        try {
            const [scan, events] = await Promise.all([api.scan(scanId), api.scanEvents(scanId, { limit: 1000 })]);
            const eventList = Array.isArray(events) ? events : [];
            const synthetic = syntheticEventsFromRun(scan);
            const combined = [...eventList, ...synthetic];
            const derived = deriveScan(scan, combined);
            timeline.update(derived, combined);
            renderScanDetailSummary(derived);
            setConnection("connected", "Backend connected; scan evidence loaded");
        } catch (error) {
            addLocalNotification("Scan detail unavailable", error.message, "danger");
            setConnection("error", "REST scan evidence unavailable");
        }
    }

    async function initializeSystemHealth() {
        const controller = new window.SemiSecure.ServiceHealthController(api, {
            fullContainer: document.getElementById("fullServiceHealthList"), blockchainContainer: document.getElementById("fullBlockchainHealth"),
            onSummary: ({ system, live, ready }) => {
                text("healthLiveness", String(live?.status || "UNREACHABLE").toUpperCase()); text("healthReadiness", String(ready?.status || "UNKNOWN").toUpperCase()); text("healthScanCount", system?.event_store?.scan_count || 0); const diagnostic = document.getElementById("healthDiagnosticPayload"); if (diagnostic) diagnostic.textContent = JSON.stringify({ system, live, ready }, null, 2);
            },
        });
        const refresh = () => controller.refresh().catch((error) => addLocalNotification("Health refresh failed", error.message, "danger"));
        document.getElementById("healthRefreshButton")?.addEventListener("click", refresh); await refresh(); state.refreshTimer = window.setInterval(refresh, Math.max(5000, Number(config.refreshIntervalMs) || 5000));
    }

    function initializeSocket() {
        const socket = new window.SemiSecure.SocketClient({
            namespace: config.socketNamespace || "/events",
            onEvent: mergeSocketEvent,
            onConnection: ({ state: connectionState, message }) => {
                if (connectionState === "connected") {
                    setConnection("connected", message);
                } else {
                    setConnection(
                        "connected",
                        "Backend connected; REST monitoring active"
                    );
                }
            },
            onServerReady: () => updateRefreshStamp(),
        });
        window.semiSecureSocket = socket; socket.connect();
    }

    document.addEventListener("DOMContentLoaded", async () => {
        updateClock(); window.setInterval(updateClock, 1000); initializeSocket();
        if (page === "dashboard") await initializeMainDashboard();
        else if (page === "scan-detail") await initializeScanDetail();
        else if (page === "provenance") { const controller = new window.SemiSecure.ProvenanceController(api); await controller.initializeDedicatedPage(); }
        else if (page === "system-health") await initializeSystemHealth();
        document.querySelectorAll(".timestamp-value").forEach((node) => { node.textContent = formatTime(node.textContent.trim()); });
    });

    window.addEventListener("beforeunload", () => { if (state.refreshTimer) window.clearInterval(state.refreshTimer); window.semiSecureSocket?.disconnect(); });
})();
