# Standards Control Mapping

Slides 6 and 13 claim alignment with NIST SP 800-193, ISO/IEC 27034 and SEMI
frameworks. No mapping existed behind those claims. This is that mapping, with the
honest scope of each.

Every control cites the file that implements it and, where one exists, the test or
evidence artefact that demonstrates it. A row with no evidence says so.

## NIST SP 800-193 — Platform Firmware Resiliency Guidelines

The closest fit of the three. SP 800-193 defines three functions: Protection,
Detection and Recovery. The platform implements recognisable analogues of all three
for the chips it analyses, not for its own firmware.

**Scope caveat.** SP 800-193 governs the firmware resiliency of a platform's own
components. This project applies the same three functions to semiconductor supply
chain evidence. The structure maps; the subject differs.

### Protection

| SP 800-193 principle | Implementation | Evidence |
|---|---|---|
| Authenticated update mechanism | OpenTitan attestation: canonicalise, HMAC-SHA-256, constant-time compare, lifecycle allowlist, monotonic anti-rollback counter | `app/hardware/opentitan/attestation.py`; `evidence/hardware/attestation_controls_20260903-0841.txt` — one positive and three negatives with distinct reason codes |
| Rollback protection | OpenTitan counter cannot be reused; PUF challenges are single-use with a 120s TTL | Observed rejecting stale evidence repeatedly during testing |
| Integrity of critical data | Hash-chained append-only event store | `manage.py verify-event-store` — 315 events, 25 files, zero issues |
| Protection of the root of trust | PUF challenge-response against an enrolled profile; fail-closed when absent | `tests/security/test_puf_anti_cloning.py`; envelope-stripped chip returns `NO_PUF_ENVELOPE` |
| Least privilege for update agents | `CommandRunner`: argument lists rather than a shell, bounded timeouts, path validation | `tests/hardware/test_command_runner_hardening.py` |

### Detection

| SP 800-193 principle | Implementation | Evidence |
|---|---|---|
| Detection of corrupted code | Reference-differential synthesis: candidate and known-good reference synthesised separately, netlists differenced | 8 cells against 27, policy limit 4; `evidence/hardware/yosys_structural_delta_evidence.json` |
| Detection of corrupted behaviour | Verilator assertion execution with an explicit pass marker | `tests/hardware/` — reference passes, Trojan payload asserts |
| Detection by measurement | Side-channel margin against a known-good baseline | clean 0.2838, Trojan 0.4637, threshold 0.35, 0/8 FP, 0/8 FN |
| Detection of anomalous state | Three-model ensemble with policy fusion above it | ROC-AUC 0.9911 on the declared corpus |
| Detection of detector degradation | Drift monitoring against the fitted training support | `evidence/ai/drift/` — flagged `sbom_mismatch_ratio` at 5.267 deviations |
| Integrity verification on demand | Event-store chain verification, restorable backup verification | `backup_restore.sh verify` — 834 files, 417 events, chain valid |

### Recovery

| SP 800-193 principle | Implementation | Evidence |
|---|---|---|
| Recovery of corrupted data | Event-store `verify_all()` and `rebuild()` | `tests/integration/test_json_event_recovery.py` |
| Recovery to a known-good state | Model rollback targets with digest-verified lineage | `models/registry/index.json` — `lineage consistent: true`, two targets |
| Resilience against failed components | Fail-closed staging at PUF, hardware, AI and blockchain; `INFRASTRUCTURE_HOLD` rather than silent approval | Verified with Fabric stopped |
| Service restoration | systemd supervision | SIGKILL PID 13586, recovered as PID 14229 in 15 seconds |
| Backup integrity | Restore verified against a scratch directory, live data untouched | `make semi-restore-check` |

**Not implemented:** SP 800-193 requires protection of the platform's *own* firmware
and a hardware root of trust. This platform has neither: the OpenTitan trust anchor is
self-signed and discloses that in `configs/hardware/opentitan.json`, and there is no
HSM. Recorded as RISK-12 and RISK-02.

## ISO/IEC 27034 — Application Security

A partial fit. 27034 defines an Application Security Management Process and an
Organization Normative Framework. The platform implements parts of the process; it
has no organisational framework, being a single-developer project.

| 27034 element | Implementation | Evidence |
|---|---|---|
| Application security risk assessment | Threat model with five trust boundaries; risk register with seventeen entries | `docs/security/THREAT_MODEL.md`, `docs/security/RISK_REGISTER.md` |
| Application normative framework | Six architectural invariants that contributions must preserve | `CONTRIBUTING.md` |
| Application security controls | Headers with CSP, rate limiting, schema validation, secret redaction, path-traversal rejection, read-only dashboard | `tests/security/` — five files, all passing |
| Verification and audit | 245 tests; CI on every push with Yosys and Verilator installed | `.github/workflows/ci.yml` |
| Security in the lifecycle | Pre-commit hooks including `detect-private-key`; Bandit; pip-audit; lockfile; self-SBOM | `evidence/security/` — Bandit 0 high, 0 medium across 13,957 lines |

**Not implemented:** no Organization Normative Framework, no formal application
security control library, no third-party assurance. A single-developer project has no
organisational layer to map.

## SEMI standards — out of scope

Slides 6 and 13 cite SEMI frameworks. The relevant ones are **SEMI E187**
(cybersecurity for fab equipment) and **SEMI E188** (malware-free equipment
integration). Both govern the security of equipment installed in a semiconductor
fabrication facility: the computers, controllers and networks attached to process
tools.

This platform is an analysis system, not fab equipment. It does not run on a process
tool, does not connect to a fab network, and does not integrate with an equipment
supplier's delivery process.

**No mapping is claimed.** Asserting alignment with a standard whose scope the project
does not enter would be the same class of unsupported claim this mapping exists to
remove. The slides should cite NIST SP 800-193 and ISO/IEC 27034, and drop SEMI.
