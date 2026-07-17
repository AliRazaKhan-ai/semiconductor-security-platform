(() => {
    "use strict";

    const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character]));

    function stateClass(healthy, status = "") {
        if (healthy === true) return "healthy";
        if (healthy === false) return "unhealthy";
        const text = String(status).toLowerCase();
        if (["ready", "alive", "available", "initialised", "connected", "enabled"].some((token) => text.includes(token))) return "healthy";
        if (["not_ready", "unavailable", "missing", "failed", "error"].some((token) => text.includes(token))) return "unhealthy";
        return "degraded";
    }

    function humanize(value) { return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase()); }

    class ServiceHealthController {
        constructor(api, { compactContainer = null, fullContainer = null, blockchainContainer = null, onSummary = () => {} } = {}) {
            this.api = api;
            this.compactContainer = compactContainer;
            this.fullContainer = fullContainer;
            this.blockchainContainer = blockchainContainer;
            this.onSummary = onSummary;
            this.latest = null;
        }

        async refresh() {
            const [systemResult, liveResult, readyResult, blockchainResult] = await Promise.allSettled([
                this.api.systemStatus(), this.api.liveness(), this.api.readiness(), this.api.blockchainStatus(),
            ]);
            const system = systemResult.status === "fulfilled" ? systemResult.value : null;
            const live = liveResult.status === "fulfilled" ? liveResult.value : null;
            const ready = readyResult.status === "fulfilled" ? readyResult.value : system?.readiness || null;
            const blockchain = blockchainResult.status === "fulfilled" ? blockchainResult.value : null;
            const checks = Array.isArray(ready?.checks) ? ready.checks : [];
            const services = [
                { name: "Flask API", healthy: live?.status === "alive", status: live?.status || "unreachable", detail: "REST and dashboard process" },
                ...checks.map((check) => ({ name: humanize(check.name), healthy: check.healthy, status: check.status, detail: check.details?.path || "Readiness dependency" })),
                { name: "JSON Event Store", healthy: Boolean(system?.database?.type === "json_event_store"), status: system?.database?.type || "unknown", detail: `${system?.event_store?.scan_count || 0} indexed scans` },
                { name: "Authentication", healthy: system?.authentication?.enabled === false, status: system?.authentication?.enabled ? "enabled" : "disabled by design", detail: "No login or user management" },
            ];
            this.latest = { system, live, ready, blockchain, services };
            this.renderServices(services);
            this.renderBlockchain(blockchain);
            const healthyCount = services.filter((service) => stateClass(service.healthy, service.status) === "healthy").length;
            this.onSummary({ healthy: healthyCount, total: services.length, system, live, ready, blockchain });
            return this.latest;
        }

        renderServices(services) {
            const renderInto = (container, list) => {
                if (!container) return;
                container.replaceChildren(...list.map((service) => {
                    const state = stateClass(service.healthy, service.status);
                    const item = document.createElement("div");
                    item.className = `service-health-item ${state}`;
                    item.innerHTML = `<span class="service-dot"></span><div><strong>${escapeHTML(service.name)}</strong><span>${escapeHTML(service.detail)}</span></div><small>${escapeHTML(humanize(service.status))}</small>`;
                    return item;
                }));
            };
            renderInto(this.compactContainer, services.slice(0, 6));
            renderInto(this.fullContainer, services);
        }

        renderBlockchain(blockchain) {
            if (!this.blockchainContainer) return;
            const fabric = blockchain?.hyperledger_fabric || {};
            const ethereum = blockchain?.ethereum_anchor || {};
            const items = [
                { name: "Hyperledger Fabric", enabled: fabric.enabled, status: fabric.connection_state || "unknown", detail: "Permissioned provenance ledger" },
                { name: "Ethereum Anchor", enabled: ethereum.enabled, status: ethereum.connection_state || "unknown", detail: "Public hash anchoring" },
                { name: "Authoritative Storage", enabled: true, status: blockchain?.authoritative_storage || "json_event_store", detail: "Operational source of truth" },
            ];
            this.blockchainContainer.replaceChildren(...items.map((item) => {
                const state = item.enabled ? stateClass(null, item.status) : "degraded";
                const node = document.createElement("div");
                node.className = `service-health-item ${state}`;
                node.innerHTML = `<span class="service-dot"></span><div><strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.detail)}</span></div><small>${escapeHTML(item.enabled ? humanize(item.status) : "Disabled")}</small>`;
                return node;
            }));
        }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.ServiceHealthController = ServiceHealthController;
    window.SemiSecure.healthStateClass = stateClass;
})();
