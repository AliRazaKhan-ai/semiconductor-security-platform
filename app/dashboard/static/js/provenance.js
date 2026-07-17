(() => {
    "use strict";

    const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character]));

    function fragment(value, length = 18) { const text = String(value || "—"); return text.length > length ? `${text.slice(0, length)}…` : text; }
    function stateFrom(enabled, state) {
        const value = String(state || "").toLowerCase();
        if (!enabled) return { label: "DISABLED", css: "neutral" };
        if (value.includes("connected") || value.includes("committed") || value.includes("confirmed")) return { label: value.toUpperCase(), css: "approved" };
        if (value.includes("failed") || value.includes("error")) return { label: value.toUpperCase(), css: "rejected" };
        return { label: value ? value.toUpperCase().replaceAll("_", " ") : "WAITING", css: "processing" };
    }

    class ProvenanceController {
        constructor(api) { this.api = api; }

        async updatePanel(scans, eventsByScan = new Map()) {
            let status = null;
            try { status = await this.api.blockchainStatus(); } catch (_) { status = null; }
            const fabric = status?.hyperledger_fabric || {};
            const ethereum = status?.ethereum_anchor || {};
            const fabricState = stateFrom(fabric.enabled, fabric.connection_state);
            const ethereumState = stateFrom(ethereum.enabled, ethereum.connection_state);
            this._setState("fabricBadge", fabricState); this._setState("ethereumBadge", ethereumState);
            this._text("fabricState", fabric.enabled ? `Connection: ${fabric.connection_state || "unknown"}` : "Disabled in configuration");
            this._text("ethereumState", ethereum.enabled ? `Connection: ${ethereum.connection_state || "unknown"}` : "Disabled in configuration");
            const overall = document.getElementById("blockchainOverall");
            if (overall) {
                const healthy = fabricState.css === "approved" && ethereumState.css === "approved";
                const enabled = fabric.enabled || ethereum.enabled;
                overall.textContent = healthy ? "OPERATIONAL" : enabled ? "PENDING" : "NOT INITIALISED";
                overall.className = `status-badge ${healthy ? "approved" : enabled ? "processing" : "neutral"}`;
            }

            let latestFabric = null; let latestEthereum = null; let latestHash = null;
            scans.forEach((scan) => {
                const events = eventsByScan.get(scan.scan_id) || [];
                events.forEach((event) => {
                    const type = String(event.event_type || "");
                    if (type === "fabric.committed") latestFabric = event.payload?.transaction_id || event.payload?.tx_id || event.event_id;
                    if (type === "ethereum.anchor_confirmed") latestEthereum = event.payload?.transaction_hash || event.payload?.tx_hash || event.event_id;
                    latestHash = event.event_hash || latestHash;
                });
                latestHash = scan.last_event_hash || latestHash;
            });
            this._text("latestFabricTx", fragment(latestFabric));
            this._text("latestEthereumTx", fragment(latestEthereum));
            this._text("latestEventHash", fragment(latestHash));
            return status;
        }

        async initializeDedicatedPage() {
            const root = document.querySelector("[data-provenance-scan]");
            if (!root) return;
            const scanId = root.dataset.provenanceScan;
            if (!scanId) return;
            const [eventsResult, statusResult, provenanceResult] = await Promise.allSettled([this.api.scanEvents(scanId, { limit: 1000 }), this.api.blockchainStatus(), this.api.blockchainProvenance(scanId)]);
            const events = eventsResult.status === "fulfilled" ? eventsResult.value : [];
            const status = statusResult.status === "fulfilled" ? statusResult.value : {};
            const provenance = provenanceResult.status === "fulfilled" ? provenanceResult.value : {};
            const fabricState = stateFrom(status.hyperledger_fabric?.enabled, status.hyperledger_fabric?.connection_state);
            const ethereumState = stateFrom(status.ethereum_anchor?.enabled, status.ethereum_anchor?.connection_state);
            this._setState("provenanceFabricState", fabricState); this._setState("provenanceEthereumState", ethereumState);
            this._text("provenanceEventCount", `${events.length} events`);
            const lastHash = provenance?.fabric?.record_hash || events.at(-1)?.event_hash; if (lastHash) this._text("provenanceEventHash", lastHash);
            this._text("provenanceFabricTx", provenance?.fabric?.fabric_transaction_id || provenance?.fabric?.transaction_id || "—");
            this._text("provenanceEthereumTx", provenance?.ethereum?.transaction_hash || provenance?.fabric?.ethereum_transaction_hash || "—");
            this._text("provenanceAnchorRoot", provenance?.ethereum?.root_hash || provenance?.fabric?.ethereum_anchor_root || "—");
            const timeline = document.getElementById("provenanceTimeline");
            if (!timeline) return;
            if (!events.length) { timeline.innerHTML = '<div class="empty-state"><span>⬡</span><p>No provenance events are available.</p></div>'; return; }
            timeline.replaceChildren(...events.map((event) => {
                const item = document.createElement("article");
                item.className = "provenance-event";
                item.innerHTML = `<div class="sequence">${event.sequence}</div><div><strong>${escapeHTML(event.event_type)}</strong><span>${escapeHTML(event.pipeline_stage)} · ${new Date(event.timestamp_utc).toLocaleString()}</span></div><code title="${event.event_hash}">${escapeHTML(fragment(event.event_hash, 24))}</code>`;
                return item;
            }));
        }

        _setState(id, state) { const node = document.getElementById(id); if (node) { node.textContent = state.label; node.className = `${node.classList.contains("mini-state") ? "mini-state" : "status-badge"} ${state.css}`; } }
        _text(id, value) { const node = document.getElementById(id); if (node) node.textContent = value ?? "—"; }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.ProvenanceController = ProvenanceController;
})();
