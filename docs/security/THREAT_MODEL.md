# Threat Model

Status: current as of the final security audit.
Scope: the SemiSecure platform as deployed, not as proposed.

The reasoning in this document already existed across SECURITY.md, README.md,
CONTRIBUTING.md and LICENSE. It had never been assembled, so control decisions
looked like omissions rather than choices. That is what this corrects.

## 1. What is being protected

| Asset | Where it lives | Why it matters |
|---|---|---|
| Provenance evidence | `data/event_store/`, Fabric ledger | The integrity claim rests on it |
| Compliance decisions | `data/compliance/decisions/` | Export-control determinations |
| Government audit packages | `data/compliance/government_audit/` | Signed, chain-bound, externally facing |
| PUF enrolments | `data/puf/enrollments/` (0700, files 0600) | Device identity root |
| Ethereum signing key | `SEMISURE_ETHEREUM_PRIVATE_KEY`, environment | Anchoring authority |
| Fabric MSP material | Filesystem, outside the repository | Ledger write authority |
| Model artefacts | `models/`, digest-bound to corpus and split | Detection integrity |

## 2. Trust boundaries

Five boundaries exist. Only one is a network edge.

1. **Terminal to platform.** The primary boundary. The operating-system account
   is the trust anchor: a user with shell access already holds `.env`, the data
   directory and the MSP material.
2. **Platform to external tool processes.** Yosys, Verilator and `peer` run as
   subprocesses through `CommandRunner`: argument lists rather than a shell,
   bounded timeouts, path validation.
3. **Platform to Fabric.** TLS to peer and orderer with MSP identity.
4. **Platform to Ethereum RPC.** Signing key from the environment, never config.
5. **Platform to browser.** One direction, read-only, GET-only client with a
   server-side test enforcing it.

## 3. Adversaries considered

**In scope.**

*A malicious foundry or design supplier* inserting a hardware Trojan. Countered
by reference-differential synthesis: the candidate and a known-good reference are
synthesised separately and the netlists differenced. Measured on the controlled
fixture at 8 cells against 27, against a policy limit of 4.

*A substituted or counterfeit component.* Countered by digital-twin binding
across six digests: chip identity, PUF identity, RTL, netlist, firmware and SBOM.

*A replayed device identity.* Countered by single-use PUF challenges with a
120-second TTL and a monotonic OpenTitan counter. Both observed rejecting stale
evidence during testing.

*A denied party in the transaction.* Partially countered. Consolidated Screening
List matching runs against the end user with a deny threshold of 96 and a review
threshold of 82. **The supplier is not screened** — see RISK-03.

*Tampering with recorded evidence.* Countered by a hash-chained append-only event
store, verifiable by `manage.py verify-event-store`. Last verification: 315
events across 25 files, zero issues.

**Out of scope, by decision.**

*A local user with shell access.* Treated as trusted. This is the model's
foundation, not an oversight.

*A network attacker.* Excluded by deployment constraint: the service binds
loopback and SECURITY.md requires a controlled network, gateway or mTLS
terminator in front of it.

*An authorised writer rewriting the event store.* Hash-chaining detects
corruption, not an authorised rewrite. External anchoring to Fabric and Ethereum
is the answer, and it only covers runs that reach the blockchain stage.

## 4. Why there is no application authentication

Deliberate, recorded in SECURITY.md and held as an invariant in CONTRIBUTING.md.

Trust is anchored at the operating-system boundary. A login on a loopback-bound
service protects nothing an attacker with shell access does not already hold.
The compensating controls are named: controlled network, firewall restrictions,
operating-system access control, and a gateway or mTLS terminator where the
service must be reachable.

Two places where this genuinely costs something are recorded as RISK-04 and
RISK-05 rather than argued away.

## 5. Implemented controls

Security headers with CSP · rate limiting, 120/60s general and 20/60s submission ·
jsonschema request validation · correlation IDs · secret redaction across eight
patterns · read-only dashboard enforced at three layers · path-traversal
rejection · subprocess hardening · loopback binding in every environment ·
fail-closed staging at PUF, hardware, AI and blockchain · confidentiality by
contract ABI, where the Ethereum anchor accepts a `bytes32` root and nothing else.

Every one of these is covered by a test.

## 6. What this model does not claim

No physical hardware validation: analysis is RTL, netlist and derived-trace based.
No production deployment: single host, local Fabric test-network, local Anvil.
No protection against a compromised operating-system account.
