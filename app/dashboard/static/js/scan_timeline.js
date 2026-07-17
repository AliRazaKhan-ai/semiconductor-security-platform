(() => {
    "use strict";

    const STAGES = Object.freeze([
        ["INGESTION", "Terminal JSON", "Schema and evidence manifest"],
        ["PUF", "PUF Authentication", "Physical chip identity"],
        ["OPENTITAN", "OpenTitan", "Root-of-trust attestation"],
        ["CHIPWHISPERER", "ChipWhisperer", "Power, timing, and EM"],
        ["YOSYS", "Yosys", "RTL and netlist analysis"],
        ["VERILATOR", "Verilator", "Behavioural simulation"],
        ["DIGITAL_TWIN", "Digital Twin", "Lifecycle reconciliation"],
        ["FEATURE_EXTRACTION", "Feature Extraction", "Trusted model inputs"],
        ["TENSORFLOW", "TensorFlow", "Known Trojan classifier"],
        ["PYTORCH", "PyTorch", "Unknown anomaly detector"],
        ["RISK", "Risk Engine", "Explainable score fusion"],
        ["COMPLIANCE", "Compliance", "ITAR, EAR, end use"],
        ["FABRIC", "Hyperledger Fabric", "Permissioned provenance"],
        ["ETHEREUM", "Ethereum Anchor", "External hash timestamp"],
        ["DEPLOYMENT", "Deployment Decision", "Critical infrastructure gate"],
    ]);

    const ALIASES = Object.freeze({
        SCAN: "INGESTION", API: "INGESTION", PUF_AUTHENTICATION: "PUF", OPEN_TITAN: "OPENTITAN",
        SIDE_CHANNEL: "CHIPWHISPERER", FEATURE: "FEATURE_EXTRACTION", TENSOR_FLOW: "TENSORFLOW",
        PY_TORCH: "PYTORCH", RISK_ENGINE: "RISK", COMPLIANCE_ENGINE: "COMPLIANCE",
        HYPERLEDGER: "FABRIC", HYPERLEDGER_FABRIC: "FABRIC", ETHEREUM_ANCHOR: "ETHEREUM",
        DEPLOYMENT_DECISION: "DEPLOYMENT",
    });

    function canonicalStage(value) {
        const normalized = String(value || "").trim().toUpperCase().replace(/[\s-]+/g, "_");
        return ALIASES[normalized] || normalized;
    }

    function eventState(event) {
        const type = String(event?.event_type || "").toLowerCase();
        const payloadStatus = String(event?.payload?.status || "").toUpperCase();
        if (type.includes("failed") || type.includes("rejected") || type.includes("quarantined") || ["FAILED", "REJECTED", "QUARANTINED"].includes(payloadStatus)) return "failed";
        if (type.includes("started")) return "active";
        if (type.includes("completed") || type.includes("committed") || type.includes("confirmed") || type.includes("approved") || type === "scan.accepted") return "passed";
        return payloadStatus === "PROCESSING" ? "active" : "passed";
    }

    class PipelineTimeline {
        constructor(container, { statusNode = null, messageNode = null, chipNode = null } = {}) {
            this.container = container;
            this.statusNode = statusNode;
            this.messageNode = messageNode;
            this.chipNode = chipNode;
            this.stageStates = new Map(STAGES.map(([key]) => [key, "waiting"]));
            this.render();
        }

        reset() {
            STAGES.forEach(([key]) => this.stageStates.set(key, "waiting"));
            this.render();
            this.setHeader({ status: "WAITING", message: "Waiting for a terminal scan.", chipId: "No active chip" });
        }

        update(scan, events = []) {
            STAGES.forEach(([key]) => this.stageStates.set(key, "waiting"));
            const ordered = [...events].sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0));
            ordered.forEach((event) => {
                const stage = canonicalStage(event.pipeline_stage);
                if (this.stageStates.has(stage)) this.stageStates.set(stage, eventState(event));
            });

            const currentStage = canonicalStage(scan?.current_stage || ordered.at(-1)?.pipeline_stage);
            const status = String(scan?.status || scan?.latest_payload?.status || "WAITING").toUpperCase();
            if (this.stageStates.has(currentStage)) {
                if (["REJECTED", "FAILED", "QUARANTINED"].includes(status)) this.stageStates.set(currentStage, "failed");
                else if (!["APPROVED"].includes(status) && this.stageStates.get(currentStage) === "waiting") this.stageStates.set(currentStage, "active");
            }
            const currentIndex = STAGES.findIndex(([key]) => key === currentStage);
            if (currentIndex >= 0) {
                for (let index = 0; index < currentIndex; index += 1) {
                    const key = STAGES[index][0];
                    if (this.stageStates.get(key) === "waiting") this.stageStates.set(key, "passed");
                }
            }
            if (status === "APPROVED") STAGES.forEach(([key]) => this.stageStates.set(key, "passed"));
            this.render();
            const lastEvent = ordered.at(-1);
            this.setHeader({
                status,
                chipId: scan?.chip_id || lastEvent?.chip_id || "Unknown chip",
                message: this._message(status, currentStage, lastEvent),
            });
        }

        render() {
            if (!this.container) return;
            this.container.replaceChildren(...STAGES.map(([key, label, description], index) => {
                const state = this.stageStates.get(key) || "waiting";
                const item = document.createElement("article");
                item.className = `pipeline-stage ${state}`;
                item.setAttribute("role", "listitem");
                item.dataset.stage = key;
                item.innerHTML = `<div><span class="stage-index">${String(index + 1).padStart(2, "0")}</span><strong>${label}</strong><small>${description}</small></div><span class="stage-state">${state.toUpperCase()}</span>`;
                return item;
            }));
        }

        setHeader({ status, message, chipId }) {
            if (this.statusNode) { this.statusNode.textContent = status; this.statusNode.className = `status-badge ${String(status).toLowerCase()}`; }
            if (this.messageNode) this.messageNode.textContent = message;
            if (this.chipNode) this.chipNode.textContent = chipId;
        }

        _message(status, stage, lastEvent) {
            if (["REJECTED", "FAILED"].includes(status)) return `Pipeline stopped at ${stage || "an unknown stage"}. The chip is blocked.`;
            if (status === "QUARANTINED") return `The chip was quarantined at ${stage || "the current stage"} for manual review.`;
            if (status === "APPROVED") return "All mandatory controls passed. Deployment approval is recorded.";
            if (lastEvent?.event_type) return `${lastEvent.event_type} received from the backend event stream.`;
            return `Validation is active at ${stage || "ingestion"}.`;
        }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.PipelineTimeline = PipelineTimeline;
    window.SemiSecure.pipelineStages = STAGES;
})();
