(() => {
    "use strict";

    const COLORS = Object.freeze({
        cyan: "#00e5ff",
        cyanFill: "rgba(0, 229, 255, 0.13)",
        green: "#68ffb0",
        red: "#ff6174",
        amber: "#ffc857",
        purple: "#a886ff",
        blue: "#5da9ff",
        grid: "rgba(121, 169, 214, 0.12)",
        text: "#8fa8bf",
        panel: "rgba(10, 22, 39, 0.84)",
    });

    function numeric(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function normalizeScore(value) {
        const score = numeric(value);
        if (score === null) return null;
        const percentage = score >= 0 && score <= 1 ? score * 100 : score;
        return Math.max(0, Math.min(100, percentage));
    }

    function extractRisk(scan) {
        const payload = scan?.latest_payload || scan?.payload || {};
        const candidates = [
            scan?.risk_score,
            scan?.overall_risk,
            payload.risk_score,
            payload.overall_risk,
            payload.score,
            payload.risk?.score,
            payload.risk?.overall,
            payload.decision?.risk_score,
        ];
        for (const candidate of candidates) {
            const value = normalizeScore(candidate);
            if (value !== null) return value;
        }
        return null;
    }

    function extractSupplierRisk(scan) {
        const payload = scan?.latest_payload || scan?.payload || {};
        const candidates = [
            scan?.supplier_risk,
            payload.supplier_risk,
            payload.supplier?.risk_score,
            payload.risk?.supplier,
            payload.supply_chain?.supplier_risk,
        ];
        for (const candidate of candidates) {
            const value = normalizeScore(candidate);
            if (value !== null) return value;
        }
        return null;
    }

    function statusOf(scan) { return String(scan?.status || scan?.latest_payload?.status || "UNKNOWN").toUpperCase(); }
    function shortIdentifier(value, length = 10) { const text = String(value || "—"); return text.length > length ? `${text.slice(0, length)}…` : text; }

    class CanvasFallback {
        constructor(canvas, type) { this.canvas = canvas; this.type = type; this.data = null; }
        update(data) { this.data = data; this.draw(); }
        draw() {
            if (!this.canvas) return;
            const rect = this.canvas.getBoundingClientRect();
            const ratio = window.devicePixelRatio || 1;
            this.canvas.width = Math.max(320, rect.width * ratio);
            this.canvas.height = Math.max(180, rect.height * ratio);
            const ctx = this.canvas.getContext("2d");
            ctx.scale(ratio, ratio);
            const width = this.canvas.width / ratio;
            const height = this.canvas.height / ratio;
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = COLORS.panel;
            ctx.fillRect(0, 0, width, height);
            const values = this.data?.values || [];
            if (!values.length) return;
            if (this.type === "doughnut") this.drawDonut(ctx, width, height, values);
            else this.drawBarsOrLine(ctx, width, height, values, this.type === "line");
        }
        drawDonut(ctx, width, height, values) {
            const total = values.reduce((sum, value) => sum + value, 0) || 1;
            const colors = [COLORS.green, COLORS.red, COLORS.amber];
            let start = -Math.PI / 2;
            values.forEach((value, index) => {
                const angle = (value / total) * Math.PI * 2;
                ctx.beginPath(); ctx.arc(width / 2, height / 2, Math.min(width, height) * .30, start, start + angle); ctx.strokeStyle = colors[index % colors.length]; ctx.lineWidth = 20; ctx.stroke(); start += angle;
            });
        }
        drawBarsOrLine(ctx, width, height, values, line) {
            const pad = 28; const max = Math.max(100, ...values); const span = width - pad * 2;
            ctx.strokeStyle = COLORS.grid; ctx.fillStyle = COLORS.cyan;
            if (line) {
                ctx.beginPath();
                values.forEach((value, index) => { const x = pad + (span * index / Math.max(1, values.length - 1)); const y = height - pad - ((height - pad * 2) * value / max); if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
                ctx.strokeStyle = COLORS.cyan; ctx.lineWidth = 2; ctx.stroke();
            } else {
                const barWidth = Math.max(8, span / values.length * .55);
                values.forEach((value, index) => { const x = pad + span * (index + .5) / values.length - barWidth / 2; const barHeight = (height - pad * 2) * value / max; ctx.fillStyle = value >= 70 ? COLORS.red : value >= 40 ? COLORS.amber : COLORS.green; ctx.fillRect(x, height - pad - barHeight, barWidth, barHeight); });
            }
        }
    }

    class DashboardCharts {
        constructor() {
            this.instances = {};
            this.useChartJs = typeof window.Chart === "function";
            if (this.useChartJs) {
                window.Chart.defaults.color = COLORS.text;
                window.Chart.defaults.borderColor = COLORS.grid;
                window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
            }
        }

        initialize() {
            this.instances.risk = this._createRiskTrend(document.getElementById("riskTrendChart"));
            this.instances.goodBad = this._createGoodBad(document.getElementById("goodBadChart"));
            this.instances.supplier = this._createSupplierRisk(document.getElementById("supplierRiskChart"));
        }

        update(scans) {
            this.updateRiskTrend(scans);
            this.updateGoodBad(scans);
            this.updateSupplierRisk(scans);
        }

        updateRiskTrend(scans) {
            const points = [...scans].reverse().map((scan) => ({ label: shortIdentifier(scan.chip_id || scan.scan_id, 9), value: extractRisk(scan) })).filter((item) => item.value !== null);
            this._toggleEmpty("riskTrendEmpty", points.length === 0);
            if (!points.length) return;
            this._apply(this.instances.risk, points.map((item) => item.label), [points.map((item) => item.value)]);
        }

        updateGoodBad(scans) {
            const statuses = scans.map(statusOf);
            const values = [
                statuses.filter((status) => status === "APPROVED").length,
                statuses.filter((status) => ["REJECTED", "FAILED"].includes(status)).length,
                statuses.filter((status) => status === "QUARANTINED").length,
            ];
            const hasData = values.some((value) => value > 0);
            this._toggleEmpty("goodBadEmpty", !hasData);
            if (!hasData) return;
            this._apply(this.instances.goodBad, ["Approved", "Rejected", "Quarantined"], [values]);
        }

        updateSupplierRisk(scans) {
            const scores = scans.map((scan) => ({ label: shortIdentifier(scan.supplier_id || scan.latest_payload?.supplier_id || scan.chip_id, 9), value: extractSupplierRisk(scan) })).filter((item) => item.value !== null).slice(0, 10).reverse();
            this._toggleEmpty("supplierRiskEmpty", scores.length === 0);
            if (!scores.length) return;
            this._apply(this.instances.supplier, scores.map((item) => item.label), [scores.map((item) => item.value)]);
        }

        _createRiskTrend(canvas) {
            if (!canvas) return null;
            if (!this.useChartJs) return new CanvasFallback(canvas, "line");
            return new window.Chart(canvas, { type: "line", data: { labels: [], datasets: [{ label: "Risk score", data: [], borderColor: COLORS.cyan, backgroundColor: COLORS.cyanFill, fill: true, tension: .34, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: COLORS.cyan }] }, options: this._baseOptions({ yMax: 100 }) });
        }

        _createGoodBad(canvas) {
            if (!canvas) return null;
            if (!this.useChartJs) return new CanvasFallback(canvas, "doughnut");
            return new window.Chart(canvas, { type: "doughnut", data: { labels: [], datasets: [{ data: [], backgroundColor: [COLORS.green, COLORS.red, COLORS.amber], borderColor: "rgba(5,9,19,.8)", borderWidth: 4, hoverOffset: 5 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { boxWidth: 9, boxHeight: 9, padding: 14, usePointStyle: true } }, tooltip: { backgroundColor: "#07111f", borderColor: COLORS.grid, borderWidth: 1 } } } });
        }

        _createSupplierRisk(canvas) {
            if (!canvas) return null;
            if (!this.useChartJs) return new CanvasFallback(canvas, "bar");
            return new window.Chart(canvas, { type: "bar", data: { labels: [], datasets: [{ label: "Supplier risk", data: [], borderWidth: 1, borderRadius: 6, backgroundColor: (context) => { const value = Number(context.raw || 0); return value >= 70 ? "rgba(255,97,116,.72)" : value >= 40 ? "rgba(255,200,87,.72)" : "rgba(104,255,176,.72)"; } }] }, options: this._baseOptions({ yMax: 100, legend: false }) });
        }

        _baseOptions({ yMax = null, legend = true } = {}) {
            return { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: "index" }, scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } }, y: { beginAtZero: true, suggestedMax: yMax, max: yMax, grid: { color: COLORS.grid }, ticks: { precision: 0 } } }, plugins: { legend: { display: legend, labels: { boxWidth: 9, usePointStyle: true } }, tooltip: { backgroundColor: "#07111f", borderColor: COLORS.grid, borderWidth: 1, padding: 10, displayColors: false } } };
        }

        _apply(instance, labels, datasets) {
            if (!instance) return;
            if (instance instanceof CanvasFallback) { instance.update({ labels, values: datasets[0] || [] }); return; }
            instance.data.labels = labels;
            datasets.forEach((values, index) => { if (instance.data.datasets[index]) instance.data.datasets[index].data = values; });
            instance.update("none");
        }

        _toggleEmpty(id, empty) { const node = document.getElementById(id); if (node) node.classList.toggle("hidden", !empty); }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.DashboardCharts = DashboardCharts;
    window.SemiSecure.extractRisk = extractRisk;
    window.SemiSecure.extractSupplierRisk = extractSupplierRisk;
    window.SemiSecure.normalizeScore = normalizeScore;
})();
