(() => {
    "use strict";

    class SemiSecureSocketClient {
        constructor({ namespace = "/events", onEvent = () => {}, onConnection = () => {}, onServerReady = () => {} } = {}) {
            this.namespace = namespace;
            this.onEvent = onEvent;
            this.onConnection = onConnection;
            this.onServerReady = onServerReady;
            this.socket = null;
            this.connected = false;
        }

        connect() {
            if (typeof window.io !== "function") {
                this._notifyConnection("unavailable", "Socket.IO client unavailable; REST refresh remains active");
                return false;
            }
            if (this.socket) return true;

            this._notifyConnection("connecting", "Connecting to event stream");
            this.socket = window.io(this.namespace, {
                transports: ["websocket", "polling"],
                reconnection: true,
                reconnectionAttempts: Infinity,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 8000,
                timeout: 10000,
                withCredentials: false,
            });

            this.socket.on("connect", () => {
                this.connected = true;
                this._notifyConnection("connected", "Live event stream connected");
            });
            this.socket.on("disconnect", (reason) => {
                this.connected = false;
                this._notifyConnection("disconnected", `Event stream disconnected: ${reason}`);
            });
            this.socket.on("connect_error", (error) => {
                this.connected = false;
                this._notifyConnection("error", error?.message || "Event stream connection failed");
            });
            this.socket.on("server.ready", (message) => this.onServerReady(message));
            this.socket.on("platform.event", (event) => this.onEvent(event));
            this.socket.on("replay.batch", (message) => {
                const events = message?.data?.events;
                if (Array.isArray(events)) events.forEach((event) => this.onEvent(event));
            });
            return true;
        }

        subscribeToScan(scanId) {
            if (!this.socket || !this.connected || !scanId) return;
            this.socket.emit("subscribe", { channel: "scan", scan_id: scanId });
        }

        requestReplay(scanId, afterSequence = 0) {
            if (!this.socket || !this.connected || !scanId) return;
            this.socket.emit("replay", { scan_id: scanId, after_sequence: Math.max(0, Number(afterSequence) || 0) });
        }

        disconnect() {
            if (this.socket) this.socket.disconnect();
            this.socket = null;
            this.connected = false;
        }

        _notifyConnection(state, message) {
            this.onConnection({ state, message });
            window.dispatchEvent(new CustomEvent("semisecure:connection", { detail: { state, message } }));
        }
    }

    window.SemiSecure = window.SemiSecure || {};
    window.SemiSecure.SocketClient = SemiSecureSocketClient;
})();
