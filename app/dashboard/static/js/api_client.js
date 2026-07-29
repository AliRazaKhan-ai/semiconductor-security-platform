(() => {
    "use strict";

    class APIError extends Error {
        constructor(message, { status = 0, code = "API_ERROR", details = {}, correlationId = null } = {}) {
            super(message);
            this.name = "APIError";
            this.status = status;
            this.code = code;
            this.details = details;
            this.correlationId = correlationId;
        }
    }

    class SemiSecureAPIClient {
        constructor({ apiPrefix = "/api/v1", timeoutMs = 10000 } = {}) {
            this.apiPrefix = String(apiPrefix).replace(/\/$/, "");
            this.timeoutMs = timeoutMs;
        }

        async request(path, { signal, timeoutMs = this.timeoutMs } = {}) {
            const controller = new AbortController();
            const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
            const relayAbort = () => controller.abort();
            if (signal) {
                if (signal.aborted) controller.abort();
                else signal.addEventListener("abort", relayAbort, { once: true });
            }

            try {
                const response = await fetch(path, {
                    method: "GET",
                    headers: { "Accept": "application/json", "X-Dashboard-Mode": "read-only" },
                    cache: "no-store",
                    credentials: "same-origin",
                    signal: controller.signal,
                });
                const contentType = response.headers.get("content-type") || "";
                const body = contentType.includes("application/json") ? await response.json() : null;
                if (!response.ok) {
                    const error = body && body.error ? body.error : {};
                    throw new APIError(error.message || `Backend request failed with HTTP ${response.status}`, {
                        status: response.status,
                        code: error.code || "HTTP_ERROR",
                        details: error.details || {},
                        correlationId: body ? body.correlation_id : null,
                    });
                }
                if (body && Object.prototype.hasOwnProperty.call(body, "ok")) {
                    if (!body.ok) {
                        throw new APIError(body.error?.message || "Backend request failed", {
                            status: response.status,
                            code: body.error?.code,
                            details: body.error?.details,
                            correlationId: body.correlation_id,
                        });
                    }
                    return body.data;
                }
                return body;
            } catch (error) {
                if (error.name === "AbortError") {
                    throw new APIError("Backend request timed out", { code: "REQUEST_TIMEOUT" });
                }
                if (error instanceof APIError) throw error;
                throw new APIError(error.message || "Unable to reach backend", { code: "NETWORK_ERROR" });
            } finally {
                window.clearTimeout(timeout);
                if (signal) signal.removeEventListener("abort", relayAbort);
            }
        }

        latestScans(limit = 50) { return this.request(`${this.apiPrefix}/scans/latest?limit=${encodeURIComponent(limit)}`); }
        scan(scanId) { return this.request(`${this.apiPrefix}/scans/${encodeURIComponent(scanId)}`); }
        scanEvents(scanId, { afterSequence = 0, limit = 500 } = {}) {
            return this.request(`${this.apiPrefix}/scans/${encodeURIComponent(scanId)}/events?after_sequence=${encodeURIComponent(afterSequence)}&limit=${encodeURIComponent(limit)}`);
        }
        chipHistory(chipId) { return this.request(`${this.apiPrefix}/chips/${encodeURIComponent(chipId)}/history`); }

        integrationRun(scanId) {
            return this.request(
                `${this.apiPrefix}/integration/runs/${encodeURIComponent(scanId)}`
            );
        }

        systemStatus() { return this.request(`${this.apiPrefix}/system/status`); }
        blockchainStatus() { return this.request(`${this.apiPrefix}/blockchain/status`); }
        blockchainProvenance(scanId) { return this.request(`${this.apiPrefix}/blockchain/provenance/${encodeURIComponent(scanId)}`); }
        liveness() { return this.request("/health/live"); }
        readiness() { return this.request("/health/ready"); }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.APIError = APIError;
    window.SemiSecure.APIClient = SemiSecureAPIClient;
})();
