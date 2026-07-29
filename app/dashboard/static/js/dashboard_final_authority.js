(() => {
    "use strict";

    const API = "/api/v1";
    let refreshTimer = null;

    const byId = (id) => document.getElementById(id);

    const setText = (id, value) => {
        const node = byId(id);
        if (node) node.textContent = value ?? "—";
    };

    const normalise = (value) => {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return null;
        }

        return number <= 1
            ? number * 100
            : number;
    };

    const classify = (scan) => {
        const status = String(
            scan?.status || ""
        ).toUpperCase();

        const decision = String(
            scan?.deployment_decision || ""
        ).toUpperCase();

        if (
            status === "MANUAL_REVIEW"
            || status === "LICENSE_REQUIRED"
            || decision.includes("PENDING_REVIEW")
            || decision.includes("PENDING_LICENSE")
            || decision.includes("HUMAN_REVIEW")
        ) {
            return "MANUAL_REVIEW";
        }

        if (
            status === "REJECTED"
            || decision.includes("REJECTED_PERMANENTLY")
        ) {
            return "REJECTED";
        }

        if (
            scan?.quarantined === true
            || decision.includes("QUARANTIN")
            || decision.includes("HOLD_FOR_RETEST")
        ) {
            return "QUARANTINED";
        }

        if (
            decision === "DEPLOY"
            || decision === "ALLOW"
            || decision === "APPROVED"
            || decision.includes("APPROVED_FOR")
            || (
                status === "COMPLETED"
                && !decision
            )
        ) {
            return "APPROVED";
        }

        if (
            status === "STOPPED"
            || status === "FAILED"
        ) {
            return scan?.quarantined
                ? "QUARANTINED"
                : "REJECTED";
        }

        return status || "UNKNOWN";
    };

    const request = async (path) => {
        const response = await fetch(path, {
            method: "GET",
            headers: {
                Accept: "application/json",
                "X-Dashboard-Mode": "read-only",
            },
            cache: "no-store",
            credentials: "same-origin",
        });

        if (!response.ok) {
            throw new Error(
                `Dashboard API returned HTTP ${response.status}`
            );
        }

        const body = await response.json();

        return Object.prototype.hasOwnProperty.call(
            body,
            "data"
        )
            ? body.data
            : body;
    };

    const setConnected = () => {
        const pill = byId("connectionPill");
        const label = byId("connectionText");

        if (pill) {
            pill.dataset.state = "connected";
            pill.classList.remove(
                "disconnected",
                "error",
                "connecting"
            );
            pill.classList.add("connected");
        }

        if (label) {
            label.textContent = "Backend connected";
        }
    };

    const removeWebSocketNoise = () => {
        document
            .querySelectorAll(
                "#notificationPanelList > *, " +
                "#notificationDrawerList > *"
            )
            .forEach((node) => {
                const message = String(
                    node.textContent || ""
                ).toLowerCase();

                if (
                    message.includes("websocket error")
                    || message.includes(
                        "live event stream unavailable"
                    )
                    || message.includes(
                        "event stream status"
                    )
                ) {
                    node.remove();
                }
            });

        const count = byId("notificationCount");

        if (count) {
            const remaining = document.querySelectorAll(
                "#notificationDrawerList > *"
            ).length;

            count.textContent = String(
                Math.max(0, remaining)
            );
        }
    };

    const updateKpis = (scans) => {
        const statuses = scans.map(classify);

        const risks = scans
            .map((scan) => normalise(
                scan.risk_score
                ?? scan.overall_risk
            ))
            .filter((value) => value !== null);

        const averageRisk = risks.length
            ? (
                risks.reduce(
                    (total, value) => total + value,
                    0
                ) / risks.length
            )
            : 0;

        const highRisk = scans.filter((scan) => {
            const risk = normalise(
                scan.risk_score
                ?? scan.overall_risk
            );

            return (
                risk !== null
                && risk >= 70
                && classify(scan) !== "APPROVED"
            );
        }).length;

        const fabricCommits = scans.filter(
            (scan) => (
                scan.fabric_committed === true
                || scan.blockchain?.fabric?.committed === true
                || scan.compliance?.blockchain?.fabric
                    ?.committed === true
            )
        ).length;

        setText("kpiTotalScans", scans.length);

        setText(
            "kpiApproved",
            statuses.filter(
                (value) => value === "APPROVED"
            ).length
        );

        setText(
            "kpiRejected",
            statuses.filter(
                (value) => value === "REJECTED"
            ).length
        );

        setText(
            "kpiQuarantined",
            statuses.filter(
                (value) => value === "QUARANTINED"
            ).length
        );

        setText(
            "kpiManualReview",
            statuses.filter(
                (value) => value === "MANUAL_REVIEW"
            ).length
        );

        setText(
            "kpiAverageRisk",
            averageRisk.toFixed(1)
        );

        setText("kpiHighRisk", highRisk);
        setText("kpiFabricCommits", fabricCommits);
    };

    const updateVerdictChart = (scans) => {
        if (
            !window.Chart
            || typeof window.Chart.getChart !== "function"
        ) {
            return;
        }

        const chart = window.Chart.getChart(
            "goodBadChart"
        );

        if (!chart) {
            return;
        }

        const statuses = scans.map(classify);

        chart.data.labels = [
            "Approved",
            "Rejected",
            "Quarantined",
            "Manual Review",
        ];

        chart.data.datasets[0].data = [
            statuses.filter(
                (value) => value === "APPROVED"
            ).length,
            statuses.filter(
                (value) => value === "REJECTED"
            ).length,
            statuses.filter(
                (value) => value === "QUARANTINED"
            ).length,
            statuses.filter(
                (value) => value === "MANUAL_REVIEW"
            ).length,
        ];

        if (
            Array.isArray(
                chart.data.datasets[0].backgroundColor
            )
        ) {
            const colours =
                chart.data.datasets[0].backgroundColor;

            while (colours.length < 4) {
                colours.push(
                    "rgba(167, 139, 250, 0.95)"
                );
            }
        }

        chart.update("none");
    };

    const setPipelineStage = (
        name,
        state,
        label
    ) => {
        const wanted = name.toUpperCase();

        const card = [
            ...document.querySelectorAll(
                "#pipelineTrack .pipeline-stage"
            ),
        ].find((node) => {
            const text = String(
                node.querySelector("strong")?.textContent
                || ""
            ).toUpperCase();

            return text.includes(wanted);
        });

        if (!card) {
            return;
        }

        card.classList.remove(
            "waiting",
            "active",
            "passed",
            "failed",
            "stopped"
        );

        card.classList.add(state);

        const badge = card.querySelector(
            ".stage-state, .status-badge, " +
            ".mini-state"
        );

        if (badge) {
            badge.textContent = label;
        }
    };

    const updatePipeline = (scan) => {
        if (!scan) {
            return;
        }

        const stopped = String(
            scan.stopped_stage || ""
        ).toUpperCase();

        const status = classify(scan);

        setText("pipelineChip", scan.chip_id);
        setText("pipelineStatus", status);

        if (stopped === "PUF_AUTHENTICATION") {
            setPipelineStage(
                "Terminal JSON",
                "passed",
                "PASSED"
            );

            setPipelineStage(
                "PUF Authentication",
                "failed",
                "FAILED"
            );

            [
                "OpenTitan",
                "ChipWhisperer",
                "Yosys",
                "Verilator",
                "Digital Twin",
                "Feature Extraction",
                "TensorFlow",
                "PyTorch",
                "Risk Engine",
                "Compliance",
                "Hyperledger Fabric",
                "Ethereum Anchor",
                "Deployment Decision",
            ].forEach((name) => {
                setPipelineStage(
                    name,
                    "waiting",
                    "NOT EXECUTED"
                );
            });

            setText(
                "pipelineMessage",
                "Pipeline stopped at PUF authentication. " +
                "The chip was quarantined because its " +
                "physical identity could not be trusted."
            );
        }
    };

    const updateExecutionPanels = (scan) => {
        if (!scan) {
            return;
        }

        const stopped = String(
            scan.stopped_stage || ""
        ).toUpperCase();

        if (stopped !== "PUF_AUTHENTICATION") {
            return;
        }

        setText("hardwareOverall", "SECURITY FAILURE");

        const modules = [
            ...document.querySelectorAll(
                "#hardwareModules .security-module"
            ),
        ];

        modules.forEach((module, index) => {
            const value = module.querySelector("strong");

            module.classList.remove(
                "passed",
                "failed"
            );

            if (index === 0) {
                module.classList.add("failed");

                if (value) {
                    value.textContent = "Failed";
                }
            } else if (value) {
                value.textContent = "Not executed";
            }
        });

        setText("aiOverall", "NOT EXECUTED");
        setText("tensorflowValue", "Not executed");
        setText("pytorchValue", "Not executed");
        setText(
            "riskFusionValue",
            normalise(scan.risk_score)?.toFixed(1)
            ?? "—"
        );
        setText("modelIntegrityValue", "Not reached");

        setText("complianceOverall", "NOT EXECUTED");
        setText("complianceScore", "—");

        const meter = byId("complianceMeter");

        if (meter) {
            meter.style.width = "0%";
        }

        document
            .querySelectorAll(
                "#complianceChecklist strong"
            )
            .forEach((node) => {
                node.textContent = "Not executed";
            });
    };

    const removeReadOnlyLabels = () => {
        document.querySelectorAll(
            ".control-lock, .dashboard-footer"
        ).forEach((node) => {
            const content = String(
                node.textContent || ""
            ).toLowerCase();

            if (
                content.includes("read-only")
                || content.includes(
                    "no dashboard controls"
                )
            ) {
                node.style.display = "none";
            }
        });

        document.querySelectorAll(
            ".eyebrow"
        ).forEach((node) => {
            node.textContent = node.textContent
                .replace(/READ-ONLY,?\s*/gi, "")
                .replace(/REAL-TIME,\s*/gi, "REAL-TIME ");
        });
    };

    const refresh = async () => {
        try {
            const scans = await request(
                `${API}/scans/latest?limit=50`
            );

            if (!Array.isArray(scans)) {
                return;
            }

            updateKpis(scans);
            updateVerdictChart(scans);

            const latest = scans[0] || null;

            updatePipeline(latest);
            updateExecutionPanels(latest);

            await request("/health/ready");

            setConnected();
            removeWebSocketNoise();
            removeReadOnlyLabels();
        } catch (error) {
            console.error(
                "Final dashboard authority:",
                error
            );
        }
    };

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            refresh();

            refreshTimer = window.setInterval(
                refresh,
                5000
            );

            const observer = new MutationObserver(() => {
                removeWebSocketNoise();
            });

            const notificationPanel =
                byId("notificationPanelList");

            const notificationDrawer =
                byId("notificationDrawerList");

            if (notificationPanel) {
                observer.observe(notificationPanel, {
                    childList: true,
                    subtree: true,
                });
            }

            if (notificationDrawer) {
                observer.observe(notificationDrawer, {
                    childList: true,
                    subtree: true,
                });
            }
        }
    );

    window.addEventListener(
        "beforeunload",
        () => {
            if (refreshTimer !== null) {
                window.clearInterval(refreshTimer);
            }
        }
    );
})();
