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
    const statusOf = (scan) => String(scan?.status || scan?.latest_payload?.status || "UNKNOWN").toUpperCase();
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
        return [...events].reverse().filter((event) => eventTypes.includes(String(event.event_type || ""))).map((event) => event.payload || {});
    }

    function firstDefined(candidates) {
        for (const candidate of candidates) if (candidate !== undefined && candidate !== null && candidate !== "") return candidate;
        return null;
    }

    function deriveScan(scan, events = []) {
        const derived = { ...scan };
        const riskPayload = payloadCandidates(events, ["risk.updated", "stage.completed"]).find((payload) => firstDefined([payload.risk_score, payload.overall_risk, payload.risk?.score]) !== null) || {};
        const compliancePayload = payloadCandidates(events, ["compliance.completed"]).at(0) || {};
        const tfPayload = [...events].reverse().find((event) => String(event.pipeline_stage || "").toUpperCase().includes("TENSORFLOW"))?.payload || {};
        const ptPayload = [...events].reverse().find((event) => String(event.pipeline_stage || "").toUpperCase().includes("PYTORCH"))?.payload || {};
        const fabricEvent = [...events].reverse().find((event) => event.event_type === "fabric.committed");
        const ethereumEvent = [...events].reverse().find((event) => event.event_type === "ethereum.anchor_confirmed");

        derived.risk_score = firstDefined([extractRisk(scan), riskPayload.risk_score, riskPayload.overall_risk, riskPayload.risk?.score]);
        derived.supplier_risk = firstDefined([extractSupplierRisk(scan), riskPayload.supplier_risk, riskPayload.risk?.supplier, riskPayload.supplier?.risk_score]);
        derived.tensorflow_score = firstDefined([tfPayload.confidence, tfPayload.probability, tfPayload.trojan_probability, tfPayload.score]);
        derived.pytorch_score = firstDefined([ptPayload.anomaly_score, ptPayload.reconstruction_error, ptPayload.score]);
        derived.compliance = compliancePayload;
        derived.fabric_tx = firstDefined([fabricEvent?.payload?.transaction_id, fabricEvent?.payload?.tx_id]);
        derived.ethereum_tx = firstDefined([ethereumEvent?.payload?.transaction_hash, ethereumEvent?.payload?.tx_hash]);
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
        const unchanged = cached && cached.updated_at === meta.updated_at && state.eventsByScan.has(meta.scan_id);
        if (unchanged) return;
        const currentSequence = state.eventVersions.get(meta.scan_id) || 0;
        const [snapshotResult, eventsResult] = await Promise.allSettled([
            api.scan(meta.scan_id),
            api.scanEvents(meta.scan_id, { afterSequence: currentSequence, limit: 1000 }),
        ]);
        const snapshot = snapshotResult.status === "fulfilled" ? snapshotResult.value : { ...cached, ...meta };
        const currentEvents = state.eventsByScan.get(meta.scan_id) || [];
        const newEvents = eventsResult.status === "fulfilled" ? eventsResult.value : [];
        const known = new Set(currentEvents.map((event) => event.event_id));
        newEvents.forEach((event) => { if (!known.has(event.event_id)) currentEvents.push(event); });
        currentEvents.sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0));
        state.eventsByScan.set(meta.scan_id, currentEvents);
        state.eventVersions.set(meta.scan_id, Number(currentEvents.at(-1)?.sequence || snapshot.last_sequence || currentSequence));
        state.scans.set(meta.scan_id, deriveScan({ ...meta, ...snapshot }, currentEvents));
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
            await Promise.allSettled(list.slice(0, 24).map(hydrateScan));
            state.latestScanId = state.scanOrder[0] || null;
            renderDashboard();
            updateRefreshStamp();
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
        const risks = scans.map(extractRisk).filter((value) => value !== null);
        const averageRisk = risks.length ? risks.reduce((sum, value) => sum + value, 0) / risks.length : 0;
        const highRisk = scans.filter((scan) => { const risk = extractRisk(scan); return risk !== null && risk >= 70 && !["APPROVED", "REJECTED"].includes(statusOf(scan)); }).length;
        const fabricCommits = [...state.eventsByScan.values()].flat().filter((event) => event.event_type === "fabric.committed").length;
        text("kpiTotalScans", state.totalScanCount || scans.length);
        text("kpiApproved", statuses.filter((status) => status === "APPROVED").length);
        text("kpiRejected", statuses.filter((status) => ["REJECTED", "FAILED"].includes(status)).length);
        text("kpiQuarantined", statuses.filter((status) => status === "QUARANTINED").length);
        text("kpiAverageRisk", averageRisk.toFixed(1));
        text("kpiHighRisk", highRisk);
        text("kpiFabricCommits", fabricCommits);
        text("kpiHealthyServices", `${state.health.healthy}/${state.health.total}`);
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
        const modules = [
            ["PUF", "Chip authentication", ["PUF"]],
            ["OT", "OpenTitan attestation", ["OPENTITAN", "OPEN_TITAN"]],
            ["CW", "Side-channel analysis", ["CHIPWHISPERER", "SIDE_CHANNEL"]],
            ["EDA", "Yosys + Verilator", ["YOSYS", "VERILATOR"]],
        ];
        const container = document.getElementById("hardwareModules");
        if (!container) return;
        const results = modules.map(([code, description, tokens]) => ({ code, description, ...stageResult(events, tokens) }));
        container.innerHTML = results.map((result) => `<div class="security-module ${result.state}"><span>${result.code}</span><strong>${result.label}</strong><small>${result.description}</small></div>`).join("");
        const hasFailure = results.some((result) => result.state === "failed");
        const passed = results.filter((result) => result.state === "passed").length;
        setBadge("hardwareOverall", hasFailure ? "FAILED" : passed === results.length ? "VERIFIED" : scan ? "PROCESSING" : "WAITING", hasFailure ? "rejected" : passed === results.length ? "approved" : scan ? "processing" : "neutral");
    }

    function renderAI(scan, events) {
        const tf = scan?.tensorflow_score;
        const pt = scan?.pytorch_score;
        const risk = extractRisk(scan);
        text("tensorflowValue", tf === null || tf === undefined ? "—" : formatPercent(tf));
        text("pytorchValue", pt === null || pt === undefined ? "—" : formatScore(pt));
        text("riskFusionValue", risk === null ? "—" : risk.toFixed(1));
        const modelIntegrity = firstDefined([scan?.latest_payload?.model_integrity, scan?.latest_payload?.manifest_valid]);
        text("modelIntegrityValue", modelIntegrity === true ? "Verified" : modelIntegrity === false ? "Failed" : scan ? "Monitored" : "Waiting");
        const tfState = stageResult(events, ["TENSORFLOW"]); const ptState = stageResult(events, ["PYTORCH"]); const riskState = stageResult(events, ["RISK"]);
        const failed = [tfState, ptState, riskState].some((result) => result.state === "failed");
        const passed = [tfState, ptState, riskState].filter((result) => result.state === "passed").length;
        setBadge("aiOverall", failed ? "MODEL FAILURE" : passed === 3 ? "ANALYSIS COMPLETE" : scan ? "ANALYSING" : "WAITING", failed ? "rejected" : passed === 3 ? "approved" : scan ? "processing" : "neutral");
    }

    function renderCompliance(scan, events) {
        const complianceEvent = [...events].reverse().find((event) => event.event_type === "compliance.completed" || String(event.pipeline_stage || "").toUpperCase().includes("COMPLIANCE"));
        const payload = complianceEvent?.payload || scan?.compliance || {};
        const rawPassed = firstDefined([payload.passed, payload.compliant, payload.result, payload.status]);
        const passed = rawPassed === true || ["PASS", "PASSED", "COMPLIANT", "APPROVED"].includes(String(rawPassed).toUpperCase());
        const failed = rawPassed === false || ["FAIL", "FAILED", "NON_COMPLIANT", "REJECTED"].includes(String(rawPassed).toUpperCase());
        const score = firstDefined([payload.confidence, payload.score, payload.compliance_score]);
        const normalized = normalizeScore(score);
        text("complianceScore", normalized === null ? passed ? "100%" : failed ? "0%" : "—" : `${normalized.toFixed(1)}%`);
        const meter = document.getElementById("complianceMeter"); if (meter) meter.style.width = `${normalized === null ? passed ? 100 : 0 : normalized}%`;
        setBadge("complianceOverall", passed ? "PASSED" : failed ? "FAILED" : scan ? "PENDING" : "WAITING", passed ? "approved" : failed ? "rejected" : scan ? "processing" : "neutral");
        const checks = [
            ["ITAR screening", firstDefined([payload.itar, payload.itar_status])],
            ["EAR classification", firstDefined([payload.ear, payload.ear_status])],
            ["End-use validation", firstDefined([payload.end_use, payload.end_use_status])],
            ["Dual-use controls", firstDefined([payload.dual_use, payload.dual_use_status])],
        ];
        const list = document.getElementById("complianceChecklist");
        if (list) list.innerHTML = checks.map(([label, result]) => {
            const resultText = String(result ?? (passed ? "Passed" : failed ? "Failed" : "Pending"));
            const resultPassed = ["TRUE", "PASS", "PASSED", "CLEAR", "COMPLIANT"].includes(resultText.toUpperCase());
            const resultFailed = ["FALSE", "FAIL", "FAILED", "BLOCKED", "NON_COMPLIANT"].includes(resultText.toUpperCase());
            return `<div><span class="check-icon ${resultPassed ? "passed" : resultFailed ? "failed" : "neutral"}">${resultPassed ? "✓" : resultFailed ? "×" : "•"}</span><span>${label}</span><strong>${escapeHTML(resultText)}</strong></div>`;
        }).join("");
    }

    function renderInfrastructure(scan) {
        const status = statusOf(scan);
        document.querySelectorAll("[data-infrastructure]").forEach((card) => {
            const badge = card.querySelector(".mini-state");
            card.classList.remove("approved", "rejected");
            if (status === "APPROVED") { card.classList.add("approved"); badge.textContent = "APPROVED"; badge.className = "mini-state healthy"; }
            else if (["REJECTED", "FAILED", "QUARANTINED"].includes(status)) { card.classList.add("rejected"); badge.textContent = "BLOCKED"; badge.className = "mini-state failed"; }
            else { badge.textContent = "BLOCKED"; badge.className = "mini-state neutral"; }
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

    function renderNotifications() {
        const markup = state.notifications.length ? state.notifications.map((item) => `<article class="notification-item ${item.severity}"><div class="notification-glyph">${escapeHTML(item.glyph)}</div><div class="notification-copy"><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(item.message)}</span></div><time class="notification-time" datetime="${escapeHTML(item.timestamp)}">${escapeHTML(relativeTime(item.timestamp))}</time></article>`).join("") : '<div class="empty-state compact"><span>⌁</span><p>No backend events received</p></div>';
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
        text("connectionText", connectionState === "connected" ? "Live events" : connectionState === "connecting" ? "Connecting" : connectionState === "unavailable" ? "REST refresh" : "Disconnected");
        if (message && ["error", "disconnected"].includes(connectionState)) addLocalNotification("Event stream status", message, "warning");
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

    async function initializeScanDetail() {
        const root = document.getElementById("scanDetailPipeline"); if (!root) return;
        const scanId = root.dataset.scanId; if (!scanId) return;
        const timeline = new window.SemiSecure.PipelineTimeline(document.getElementById("pipelineTrack"), { statusNode: document.getElementById("pipelineStatus"), messageNode: document.getElementById("pipelineMessage") });
        try { const [scan, events] = await Promise.all([api.scan(scanId), api.scanEvents(scanId, { limit: 1000 })]); timeline.update(scan, events); } catch (error) { addLocalNotification("Scan detail unavailable", error.message, "danger"); }
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
        const socket = new window.SemiSecure.SocketClient({ namespace: config.socketNamespace || "/events", onEvent: mergeSocketEvent, onConnection: ({ state: connectionState, message }) => setConnection(connectionState, message), onServerReady: () => updateRefreshStamp() });
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
