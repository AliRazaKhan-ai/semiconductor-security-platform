# Developer Guide

## 1. Development philosophy

SemiSecure is evidence-driven and fail-secure. New code must:

- preserve immutable event history;
- avoid hidden state mutation;
- validate all external inputs;
- keep the dashboard read-only;
- avoid adding SQL or authentication unless project constraints change;
- provide deterministic tests;
- record security-relevant actions;
- fail to quarantine, rejection, or review rather than unsafe approval.

## 2. Local setup

```bash
cd ~/semiconductor_security_platform
source venv/bin/activate
python -m pip install -r requirements.txt
```

Development dependencies:

```bash
python -m pip install \
  "pytest>=8.4,<9" \
  "pytest-cov>=6.2,<7" \
  "ruff>=0.12,<1" \
  "mypy>=1.16,<2"
```

## 3. Application composition

`app/factory.py` is the only supported application composition root. Avoid creating parallel Flask applications in tests or scripts.

Use:

```python
from app.factory import create_app

app = create_app()
```

Services are available through `app.extensions`, including:

- `semisecure.event_store`
- `semisecure.audit_writer`
- `semisecure.audit_reader`
- `semisecure.socket_publisher`
- `semisecure.blockchain_service`
- `semisecure.ai_pipeline`
- `semisecure.hardware_pipeline`
- `semisecure.compliance_service`
- `semisecure.integrated_pipeline`

## 4. Package responsibilities

| Package | Responsibility |
|---|---|
| `app/domain` | entities, status, lifecycle, and domain rules |
| `app/storage` | immutable persistence, audit, indexes, recovery |
| `app/hardware` | hardware evidence, PUF, adapters, tool integration |
| `app/ai` | features, model loading, inference, explainability, risk |
| `app/compliance` | EAR, ITAR, restricted parties, supplier risk, reports |
| `app/blockchain` | Fabric provenance and Ethereum anchoring |
| `app/pipeline` | stage order and final decision routing |
| `app/integration` | integrated run service and cross-component coordination |
| `app/api` | versioned HTTP interface |
| `app/websocket` | live read-only event delivery |
| `app/dashboard` | presentation only |

Do not place policy logic in dashboard JavaScript.

## 5. Event creation

Every security-relevant transition should append an `EventRecord` through the event store.

Conceptual pattern:

```python
record = event_store.append(
    scan_id=scan_id,
    chip_id=chip_id,
    event_type=event_type,
    pipeline_stage=stage,
    correlation_id=correlation_id,
    source_component="component-name",
    component_version=version,
    payload=payload,
)

publisher = current_app.extensions.get("semisecure.socket_publisher")
if publisher is not None:
    publisher.publish_record(record)
```

Events must contain enough evidence to explain what happened without relying on mutable memory.

## 6. Adding a pipeline stage

1. Define the stage's input and output schema.
2. Implement a service with a small, typed interface.
3. Add deterministic failure behaviour.
4. Append start, result, and failure events.
5. Integrate the stage in the orchestrator.
6. Define routing consequences.
7. Add unit tests.
8. Add end-to-end fixture coverage.
9. Add dashboard projection only after backend evidence is stable.
10. Update architecture and API documentation.

A stage must never directly approve a chip. It contributes evidence to policy fusion.

## 7. Adding an API endpoint

Use a child Flask Blueprint under `app/api/routes`.

```python
from flask import Blueprint
from app.api.response import success

bp = Blueprint("example", __name__)

@bp.get("/example")
def example():
    return success({"status": "ok"})
```

Register the Blueprint in `app/api/routes/__init__.py` so it inherits `/api/v1` from the API parent Blueprint.

Requirements:

- validate inputs;
- use standard success/error envelopes;
- preserve correlation IDs;
- avoid leaking stack traces or secrets;
- include API tests;
- document status codes.

## 8. Dashboard development

The dashboard consumes API projections and Socket.IO events. It must not become an alternative control plane.

Rules:

- no POST controls for scans;
- do not infer security decisions solely in JavaScript;
- show `unknown` rather than inventing missing values;
- deduplicate notifications;
- handle disconnected WebSocket state;
- maintain REST refresh as fallback;
- escape untrusted content before inserting into the DOM.

Validate JavaScript:

```bash
node --check app/dashboard/static/js/dashboard.js
```

Run contracts:

```bash
python -m pytest tests/dashboard tests/static -q
```

## 9. WebSocket development

Namespace:

```text
/events
```

Primary server event:

```text
platform.event
```

A namespace-wide broadcast omits the `to` argument. Targeted subscriptions use rooms such as `scan:<scan_id>`.

Multi-process warning: Socket.IO events do not cross Gunicorn worker processes without a shared message queue. Keep one worker or add Redis/message-queue configuration.

## 10. Configuration

Configuration belongs under `configs/` and is loaded through `app/config_loader.py`. Avoid scattering environment lookups throughout business logic.

When adding configuration:

1. add a documented default;
2. validate its type and allowed range;
3. expose it through the loaded configuration;
4. add tests for invalid values;
5. ensure secrets come from environment variables rather than committed JSON.

## 11. Tests

Recommended test layers:

- unit tests for domain and service logic;
- schema and validation tests;
- API contract tests;
- event-store integrity and recovery tests;
- pipeline routing tests;
- dashboard static contracts;
- hardware adapter tests;
- AI model-load and inference tests;
- blockchain integration tests;
- performance tests.

Commands:

```bash
python -m pytest -q
python -m pytest tests/pipeline -q
python -m pytest tests/api -q
python -m pytest tests/dashboard tests/static -q
```

Avoid tests that depend on execution order or existing runtime data.

## 12. Formatting and static checks

```bash
ruff check app tests terminal
mypy app
python -m compileall -q app terminal
```

Project conventions:

- Python 3.12;
- type hints for public functions;
- 100-character line target;
- descriptive module docstrings;
- explicit error handling;
- no broad `except Exception` unless at a controlled integration boundary with logging.

## 13. Git workflow

```bash
git checkout -b feature/descriptive-name
git status
git diff
python -m pytest -q

git add <specific-files>
git diff --cached
git commit -m "Describe the security change"
git push -u origin feature/descriptive-name
```

Do not use `git add .` before inspecting untracked files. Never commit:

- `.env.production`;
- runtime logs and PIDs;
- generated events, audits, snapshots, or reports;
- private keys and wallets;
- virtual environments;
- model training checkpoints unless intentionally versioned;
- repair ZIPs or local review bundles.

## 14. Definition of done

A change is complete when:

- behaviour is implemented;
- failure behaviour is defined;
- tests pass;
- event and audit evidence is preserved;
- API/dashboard contracts are updated where relevant;
- documentation is updated;
- no secrets or generated runtime files are staged;
- health checks remain ready;
- a relevant end-to-end scenario has been demonstrated.
