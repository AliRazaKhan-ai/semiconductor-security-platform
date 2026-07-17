# SemiSecure Enterprise Dashboard

The dashboard is a read-only operational projection of terminal-originated semiconductor scans.

## Control boundary

- No login, user management, chip selector, scan button, approval button, or reset action is present.
- The terminal submits scans to the backend.
- The dashboard receives durable `platform.event` messages through the `/events` Socket.IO namespace.
- REST polling repairs missed events and refreshes projections when the Socket.IO connection is interrupted.
- The JSON event store and backend REST API remain authoritative.

## Main panels

The command overview contains exactly eight KPI cards, three Chart.js analytics, the complete fifteen-stage fail-closed pipeline, live scans, blockchain, compliance, hardware security, AI status, critical infrastructure, notifications, and service health.

## Browser dependencies

Bootstrap is self-hosted under `app/dashboard/static/vendor/bootstrap`. Chart.js and the Socket.IO browser client are loaded from pinned jsDelivr URLs. The dashboard includes canvas and REST refresh fallbacks so operational data remains visible when an external browser asset cannot be loaded.

## Configuration

`configs/application/dashboard.json` controls the read-only refresh interval and initial server-rendered scan count. The default refresh interval is five seconds.
