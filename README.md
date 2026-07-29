# SemiSecure Platform

**AI-Driven Semiconductor Supply Chain Security Platform**

SemiSecure is a terminal-controlled security platform for evaluating semiconductor devices and supply-chain evidence before deployment in critical infrastructure. It combines hardware-security analysis, machine-learning inference, compliance checks, supplier-risk assessment, immutable event storage, blockchain provenance, government-grade reporting, and a read-only operational dashboard.

## Core capabilities

- Hardware Trojan and anomaly detection using TensorFlow, PyTorch, and Scikit-learn.
- Physical Unclonable Function (PUF) authentication with replay protection.
- Hardware-tool integration for OpenTitan, ChipWhisperer, Yosys, Verilator, Digital Twin, and SBOM evidence.
- Supplier, geopolitical, sanctions, counterfeit, and provenance-risk analysis.
- Export-control evaluation using EAR and ITAR policy rules.
- Immutable JSON event store with hash-chain integrity and audit records.
- Hyperledger Fabric provenance and Ethereum hash anchoring.
- Read-only Flask dashboard with REST and Socket.IO updates.
- Terminal-originated scans, deterministic test scenarios, and government audit packages.

## Design principles

1. **Terminal-controlled operation:** scans originate from trusted command-line workflows.
2. **Read-only dashboard:** the browser displays evidence and decisions but does not initiate scans.
3. **No SQL database:** operational history is stored in append-only JSON events and indexes.
4. **Evidence before decision:** every verdict is traceable to hardware, AI, compliance, and provenance evidence.
5. **Defence in depth:** no single detector can approve a chip by itself.
6. **Fail secure:** severe Trojan, counterfeit, sanctions, or provenance failures cause quarantine or permanent rejection.
7. **Auditability:** decisions are reproducible, hashable, and suitable for regulator or examiner review.

## High-level workflow

```mermaid
flowchart LR
    A[Terminal chip submission] --> B[Schema validation]
    B --> C[Hardware evidence]
    C --> D[PUF and authentication]
    D --> E[AI inference]
    E --> F[Supplier and geopolitical risk]
    F --> G[EAR and ITAR checks]
    G --> H[Policy fusion]
    H --> I{Final decision}
    I -->|Approved| J[Deployment permitted]
    I -->|Quarantined| K[Isolate and investigate]
    I -->|Manual review| L[Human compliance review]
    I -->|Rejected| M[Permanent rejection]
    I --> N[Immutable event and audit records]
    N --> O[Fabric provenance]
    N --> P[Ethereum hash anchor]
    N --> Q[Read-only dashboard]
```

## Project layout

```text
app/                 Flask application and platform services
  ai/                Feature extraction, models, inference, risk fusion
  api/               Versioned REST API
  blockchain/        Fabric and Ethereum integration
  compliance/        EAR, ITAR, supplier risk, policy, and reports
  dashboard/         Read-only templates, JavaScript, charts, timeline
  hardware/          PUF and external hardware-tool integrations
  integration/       Integrated pipeline service
  pipeline/          Production orchestration and decision routing
  storage/           JSON event store, audit store, indexes, recovery
  websocket/         Socket.IO namespace, subscriptions, publishing
blockchain/          Fabric network assets and Ethereum contracts
configs/             Application, AI, compliance, and integration settings
data/                Chip fixtures and generated runtime evidence
deployment/          WSGI and container entry point
docs/                Architecture decisions, runbooks, and documentation
models/              Trained model artefacts and manifests
schemas/             API, event, hardware, and compliance schemas
scripts/             Setup, deployment, maintenance, and verification tools
terminal/            Terminal command implementation
tests/               Unit, integration, API, dashboard, and regression tests
manage.py            Main terminal entry point
```

## Requirements

- Ubuntu 22.04 or later
- Python 3.12
- Docker and Docker Compose for container or blockchain workflows
- At least 8 GB RAM; 16 GB is recommended when TensorFlow, PyTorch, Fabric, and Ethereum run together
- Git
- `curl`, build tools, and standard Linux utilities

## Quick start

```bash
git clone https://github.com/AliRazaKhan-ai/semiconductor-security-platform.git
cd semiconductor-security-platform

python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

./scripts/runtime/start_backend.sh
curl -fsS http://localhost:5000/health/ready | python -m json.tool
```

Open the dashboard:

```text
http://localhost:5000/dashboard
```

Run a terminal scan using the project's supported scan command or deployment wrapper:

```bash
scripts/deployment/run_scan.sh "$PWD" data/chips/chip_01_good.json
```

## Expected reference scenarios

| Scenario | Expected decision |
|---|---|
| Known-good chip | APPROVED |
| Hardware Trojan | QUARANTINED |
| Weak PUF | QUARANTINED |
| Supply-chain tampering | QUARANTINED |
| High-risk supplier | MANUAL_REVIEW |
| Counterfeit chip | REJECTED |
| Sanctioned manufacturer | REJECTED |
| Fake provenance | REJECTED |

## Health and verification

```bash
curl -fsS http://localhost:5000/health/live
curl -fsS http://localhost:5000/health/ready | python -m json.tool
python -m pytest -q
```

A production instance is considered ready only when `/health/ready` reports `"status": "ready"` and all required storage checks are healthy.

## Documentation

- [Architecture Guide](docs/ARCHITECTURE_GUIDE.md)
- [Installation Guide](docs/INSTALLATION_GUIDE.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [API Documentation](docs/API_DOCUMENTATION.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING_GUIDE.md)

## Security warning

Never commit `.env.production`, passwords, API tokens, Fabric private keys, Ethereum private keys, wallet identities, mnemonics, generated audit evidence, or runtime event-store content.

## Licence

Proprietary educational project by Ali Raza. Third-party components retain their respective licences.
