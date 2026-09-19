# Security Risk Register

Each entry states what was measured, not what was assumed. Treatment is either
a control that exists or an accepted residual with the reason recorded.

| ID | Risk | Likelihood | Impact | Treatment |
|---|---|---|---|---|
| RISK-01 | `torch 2.13.0+cpu` cannot be audited: the local CPU wheel is not published to PyPI, so pip-audit skips it | Low | Medium | **Accepted.** Recorded rather than suppressed. Every other dependency reports no known vulnerabilities. |
| RISK-02 | No encryption at rest. Compliance decisions, audit packages, PUF enrolments and provenance evidence are plaintext JSON | Medium | High | **Accepted for this deployment.** Filesystem permissions are the control: `data/puf/` is 0700 with 0600 files. A production deployment would hold PUF material in an HSM. |
| RISK-03 | Export control screens the end user only. The supplier is never screened, and the sole Consolidated Screening List entry is a supplier name | Medium | High | **Open.** Identified during the final audit. Remediation is to screen both parties; above the deny threshold there is no discretionary band. |
| RISK-04 | The audit trail records what happened, never who did it. `configs/application/compliance.json` mandates qualified human review the platform cannot attribute | High | Medium | **Accepted.** Attribution requires identity, which requires authentication, excluded by the threat model. A production deployment with named reviewers would need both. |
| RISK-05 | Ledger writes use a single `Admin@org1.example.com` identity. The designed five-organisation consortium exists as unprovisioned scaffolding | High | Medium | **Accepted.** Custody is hash-protected but not multi-party attested. |
| RISK-06 | Rate limiting is in-memory: it resets on restart and does not span workers. `gunicorn.conf.py` allows 32 threads; `start_backend.sh` uses one worker | Medium | Low | **Partially mitigated.** Holds under the current launch script. No test asserts single-worker deployment. |
| RISK-07 | chart.js and socket.io load from `cdn.jsdelivr.net` without SRI hashes. Bootstrap is vendored locally | Low | Medium | **Open.** A supply-chain platform executing unverified third-party JavaScript. Fix is to vendor both or add integrity hashes. |
| RISK-08 | No automated backup, no restore test, no RTO or RPO. Ten manual snapshots exist in `backups/` | Medium | High | **Accepted for this deployment.** The event store supports `verify_all()` and `rebuild()`; recovery is tested, disaster recovery is not. |
| RISK-09 | No metrics, alerting or tracing. All three observability modules are empty | Medium | Medium | **Accepted.** Health checks and structured logging exist. Drift monitoring is absent, and it is the control that would have caught the train/serve distribution break automatically. |
| RISK-10 | Detection is validated against a two-design corpus: an 8-cell reference and a 27-cell controlled Trojan | High | High | **Accepted and declared.** The dataset manifest states that any metric measures separability between those two designs, not detector performance on real silicon. |
| RISK-11 | No physical semiconductor hardware. Power, EM and timing analysis is derived from netlist metrics | Certain | High | **Accepted and enforced in code.** `physical_capture_verification` is `NOT_IMPLEMENTED` and the adapter refuses any trace claiming `PHYSICAL_CAPTURE`. |
| RISK-12 | The OpenTitan trusted firmware digest is derived from the fixture it verifies, and the HMAC key is generated locally | Certain | High | **Accepted and self-disclosed.** The disclosure is written into `configs/hardware/opentitan.json` and states what a real deployment requires. |
| RISK-13 | Evidence expires: PUF challenges are single-use with a 120-second TTL, OpenTitan attestation at 300 seconds | Certain | Low | **By design.** Anti-replay working. Minting is part of the run sequence and the integration test mints its own evidence. |
| RISK-14 | `POST /api/v1/scans` accepts unauthenticated submissions, against the terminal-controlled design principle | Low | Medium | **Accepted.** Loopback-bound. `scan_submission_enabled` exists and can be set false; the guard is implemented. |
| RISK-15 | Approval gates are documented in CONTRIBUTING.md but not enforced: no branch protection, no required status checks | Medium | Medium | **Open.** CI runs on every push; lint and type checking report without blocking while the 387-finding backlog is worked through. |
| RISK-16 | `create_app()` constructs each service in try/except, so a broken subsystem yields a running application with a silently absent capability | Medium | Medium | **Partially mitigated.** Runtime callers fail closed and a test forbids fallbacks. Startup does not fail loudly. Observed live during testing. |
| RISK-17 | Fabric containers publish 7050, 7051, 9051 and 9443-9445 on 0.0.0.0 while the application binds loopback in every environment | Low | Medium | **Open.** The fabric-samples test-network default rather than a configured choice. TLS with MSP identity still gates access, but it is wider than the boundary SECURITY.md describes. Measured with ss -ltnp; see docs/architecture/NETWORK.md. |

## Review

This register was produced during the final security audit. Entries marked Open
have no control in place. Entries marked Accepted have a reason recorded and, in
most cases, a compensating control.

The three that would matter most in a production deployment are RISK-03, RISK-04
and RISK-02, in that order.
