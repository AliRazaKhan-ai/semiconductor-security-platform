# API Documentation

## 1. Conventions

Base URL:

```text
http://localhost:5000
```

Versioned API prefix:

```text
/api/v1
```

Content type:

```text
application/json
```

The platform currently has no application login or JWT layer. Deploy it only inside a controlled network or behind an approved security gateway.

Responses use the project's standard success/error envelope. Exact metadata fields may include correlation and request information.

## 2. Health endpoints

### GET `/health/live`

Confirms that the Flask process is running.

```bash
curl -fsS http://localhost:5000/health/live
```

### GET `/health/ready`

Confirms that required storage and application extensions are ready.

```bash
curl -fsS http://localhost:5000/health/ready | python -m json.tool
```

Representative payload:

```json
{
  "status": "ready",
  "checks": [
    {
      "name": "event_store",
      "healthy": true,
      "status": "available"
    }
  ],
  "timestamp_utc": "2026-06-09T12:08:09.069+00:00"
}
```

## 3. Scan endpoints

### POST `/api/v1/scans`

Accepts a JSON scan submission. The endpoint validates the submission schema and creates the first immutable scan event.

Headers:

```text
Content-Type: application/json
Idempotency-Key: optional-client-key
```

Representative request:

```json
{
  "chip_id": "CHIP-001",
  "chip_file": "data/chips/chip_01_good.json",
  "source": {
    "type": "terminal"
  },
  "evidence": {
    "submission": "validated"
  },
  "metadata": {
    "supplier": {
      "name": "Example Supplier"
    }
  }
}
```

Example:

```bash
curl -X POST http://localhost:5000/api/v1/scans \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-chip-001' \
  --data @submission.json
```

Responses:

- `202 Accepted`: new scan event created;
- `200 OK`: idempotent replay returned;
- `400 Bad Request`: malformed JSON or validation failure;
- `409 Conflict`: submission disabled or conflicting state;
- `429 Too Many Requests`: rate limit exceeded.

### GET `/api/v1/scans/latest`

Returns recent scan projections.

Common query parameters are bounded by server validation. Use API output rather than assuming internal defaults.

```bash
curl -fsS 'http://localhost:5000/api/v1/scans/latest' \
  | python -m json.tool
```

### GET `/api/v1/scans/{scan_id}`

Returns an enriched scan snapshot, including available integrated-run evidence.

```bash
curl -fsS \
  http://localhost:5000/api/v1/scans/SCAN_ID \
  | python -m json.tool
```

### GET `/api/v1/scans/{scan_id}/events`

Returns immutable events for the scan.

```bash
curl -fsS \
  http://localhost:5000/api/v1/scans/SCAN_ID/events \
  | python -m json.tool
```

## 4. Chip history

### GET `/api/v1/chips/{chip_id}/history`

Returns scan and provenance history associated with a chip identifier.

```bash
curl -fsS \
  http://localhost:5000/api/v1/chips/CHIP-001/history \
  | python -m json.tool
```

## 5. Integrated pipeline endpoints

The integration Blueprint is registered under the versioned API. Its configured URL prefix determines the full route. In the current project, inspect `app/api/routes/integration.py` and the resolved Flask URL map before external integration.

Routes provided by the module:

- `POST /run`
- `GET /runs`
- `GET /runs/{identifier}`

Print the resolved routes:

```bash
flask --app 'app.factory:create_app' routes
```

## 6. Blockchain endpoints

### GET `/api/v1/blockchain/status`

Returns Fabric and Ethereum integration status.

```bash
curl -fsS \
  http://localhost:5000/api/v1/blockchain/status \
  | python -m json.tool
```

### GET `/api/v1/blockchain/provenance/{scan_id}`

Retrieves provenance associated with a scan.

### POST `/api/v1/blockchain/provenance`

Creates or submits a provenance record when permitted by platform configuration.

The terminal pipeline is the preferred production path. Do not expose write endpoints directly to untrusted users.

## 7. Compliance endpoints

The compliance Blueprint has its own full prefix:

```text
/api/v1/compliance
```

### GET `/api/v1/compliance/status`

Returns compliance-service readiness.

### POST `/api/v1/compliance/evaluate`

Evaluates a compliance payload.

### GET `/api/v1/compliance/scans/{scan_id}`

Returns the compliance decision for a scan.

### GET `/api/v1/compliance/scans/{scan_id}/report.json`

Downloads or returns the JSON compliance report.

### GET `/api/v1/compliance/scans/{scan_id}/report.pdf`

Returns the PDF compliance report.

### GET `/api/v1/compliance/scans/{scan_id}/government-audit`

Returns the government audit package or its metadata.

## 8. Hardware status

The hardware Blueprint is registered beneath `/api/v1` and uses `/hardware` as its local prefix.

### GET `/api/v1/hardware/status`

```bash
curl -fsS \
  http://localhost:5000/api/v1/hardware/status \
  | python -m json.tool
```

## 9. System status

### GET `/api/v1/system/status`

Returns consolidated platform status.

```bash
curl -fsS \
  http://localhost:5000/api/v1/system/status \
  | python -m json.tool
```

## 10. WebSocket API

Socket.IO namespace:

```text
/events
```

Client connection:

```javascript
const socket = io("/events");
```

Events received by the dashboard include:

- `server.ready`
- `platform.event`
- `replay.batch`
- `subscription.accepted`

The main event payload is derived from an immutable `EventRecord` and normally includes scan, chip, event type, stage, timestamp, and payload data.

Example:

```javascript
const socket = io("/events");

socket.on("platform.event", (event) => {
  console.log(event);
});
```

Room subscriptions may use scan-specific rooms such as:

```text
scan:<scan_id>
```

## 11. Error handling

Clients should handle:

- `400`: validation error;
- `404`: scan or resource not found;
- `409`: conflict or disabled operation;
- `429`: rate limit;
- `500`: controlled internal error;
- `503`: required service unavailable.

Do not parse human-readable error text as a stable contract. Use structured error fields.

## 12. Idempotency

Scan submission supports an idempotency key. The server derives a deterministic scan identifier from the chip and key when a scan ID is not supplied. Repeating the same request returns the existing snapshot instead of creating duplicate history.

## 13. API verification

List all routes:

```bash
source venv/bin/activate
flask --app 'app.factory:create_app' routes
```

Run API tests:

```bash
python -m pytest tests/api -q
```

Validate example JSON against schemas under `schemas/api/` before integrating another client.
