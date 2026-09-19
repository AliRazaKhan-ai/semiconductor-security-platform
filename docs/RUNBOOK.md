# Operational Runbook

Day-to-day operation of the SemiSecure platform on a single host. Installation is in
INSTALLATION_GUIDE.md and architecture in ARCHITECTURE_GUIDE.md.

This is not production deployment software. LICENSE prohibits use in production,
commercial, governmental, military or critical-infrastructure environments without
written permission. It runs on one host with local Fabric and Ethereum networks.

## Starting and stopping

    make semi-up        Docker, Fabric, chaincode runtime, Anvil, contract, backend
    make semi-status    what is listening
    make semi-down      stop everything

semi-up takes about 90 seconds and is health-gated at each step. It starts the Fabric
test-network if the containers are absent, verifies the channel and chaincode, starts
Anvil, and redeploys the HashAnchor contract if it is missing.

Services do not survive a VM suspend or reboot unless the systemd unit is enabled.

## Running scans

    make semi-chip001    good chip, all eight stages, deploys        ~130s
    make semi-chip002    Trojan, stops at hardware security           ~35s
    make semi-chip003    weak PUF, stops at authentication            ~35s
    make semi-chip004    supply-chain tampered, manual review
    make semi-chip005    high-risk supplier, manual review
    make semi-chip006    counterfeit, denied and quarantined
    make semi-chip007    sanctioned manufacturer, manual review
    make semi-chip008    fake provenance, manual review
    make semi-pair       chip001 and chip002                        ~165s
    make semi-all        all eight, sequential                       ~8.5m
    make semi-fast       all eight, three workers                    ~5.5m

Each chip is minted immediately before it runs. A PUF challenge is single-use with a
120-second TTL and OpenTitan attestation expires after 300 seconds, so minting the
whole set then running it leaves the earliest chip stale. This is anti-replay working.

The first run after starting Fabric costs roughly twice the second: 335s against 146s
for the good chip. Run one scan as a warm-up before any demonstration.

## Expected outcomes

| Chip | Decision | Stops at |
|---|---|---|
| chip_01_good | DEPLOY | completes all eight stages |
| chip_02_trojan | DENIED_AND_QUARANTINED | HARDWARE_SECURITY |
| chip_03_puf_unstable | HOLD_FOR_RETEST_OR_REJECT | PUF_AUTHENTICATION |
| chip_04_supplychain_tampered | DO_NOT_DEPLOY_PENDING_REVIEW | DEPLOYMENT_DECISION |
| chip_05_highrisk_supplier | DO_NOT_DEPLOY_PENDING_REVIEW | DEPLOYMENT_DECISION |
| chip_06_counterfeit | DENIED_AND_QUARANTINED | — |
| chip_07_sanctioned_manufacturer | DO_NOT_DEPLOY_PENDING_REVIEW | DEPLOYMENT_DECISION |
| chip_08_fake_provenance | DO_NOT_DEPLOY_PENDING_REVIEW | DEPLOYMENT_DECISION |

REJECTED_PERMANENTLY is never produced. It belonged to the earlier pipeline, which
assigned verdicts from the fixture's scenario label, and went when detection became
evidence-based.

## Verification

    python manage.py verify-event-store       hash chain across every partition
    make semi-restore-check                   restore the newest backup and verify it
    curl -s localhost:5000/health/ready       readiness, with degraded subsystems named
    curl -s localhost:5000/metrics            platform state, Prometheus format
    curl -s localhost:5000/alerts             firing alerts; 503 when any is firing
    pytest -q                                 245 tests

A readiness status of degraded names the subsystems that failed to construct and
returns 503. The process still runs and runtime callers fail closed.

## Backup

    make semi-backup            archive the recoverable stores
    make semi-restore-check     restore the newest archive to a scratch directory
    make semi-reset             archive, then clear the dashboard

semi-restore-check never touches live data. Archives exclude data/puf/ and
data/hardware/: those hold owner-only secret material. PUF enrolments cannot be
regenerated without SEMISURE_PUF_MASTER_SECRET.

## Common problems

**Backend unreachable, panels empty.** make semi-status, then make semi-up.

**A chip stops at PUF_AUTHENTICATION unexpectedly.** Its evidence expired. Run the
semi-chip* target, which mints first, rather than the pipeline directly.

**BLOCKCHAIN fails with connection refused.** Fabric or Anvil is down, commonly after
a suspend. make semi-up. An approved chip then returns
HOLD_PENDING_BLOCKCHAIN_RECOVERY rather than deploying, which is the fail-closed path.

**Dashboard slow or empty.** The scan store has grown; each enriched scan is about
302 KB and the endpoint returns twenty. make semi-reset.

**A scan takes much longer than expected.** Check free memory. The VM swaps below
about 1.5 GB available.

## Data locations

    data/event_store/        hash-chained append-only events
    data/audit/              separate audit trail
    data/integrated_runs/    per-run records
    data/compliance/         decisions, reports, government audit packages
    data/blockchain/         Ethereum receipts
    data/puf/                enrolments and challenge ledger, 0700, secret
    data/hardware/           OpenTitan replay counter, secret
    evidence/                captured evidence for review
    runtime/                 logs, locks, PID files
    backups/                 store archives

## What is not automated

Automatic restart is available: deployment/systemd/semisecure-backend.service
supervises the backend, restarts it within about fifteen seconds of a failure, and
starts it at boot.

    sudo cp deployment/systemd/semisecure-backend.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now semisecure-backend
    journalctl -u semisecure-backend -f

The unit owns port 5000 while enabled, so start_backend.sh and semi-up conflict with
it. `sudo systemctl disable --now semisecure-backend` returns manual control. It
supervises the backend only; Fabric and Anvil remain with semi-up.

No offsite backup. No RTO or RPO. No metrics, alerting or tracing beyond health checks
and structured logging. No on-call or escalation. These are recorded in
docs/security/RISK_REGISTER.md with the reasons they are accepted for this deployment.
