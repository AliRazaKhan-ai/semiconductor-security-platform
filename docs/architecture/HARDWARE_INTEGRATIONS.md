# Production Hardware Security Integrations

## OpenTitan
**Purpose:** verify hardware-root-of-trust evidence, secure-boot state, lifecycle state, firmware identity, and rollback protection.
**Input:** signed JSON attestation containing device ID, ROM/firmware/OTP SHA-256 digests, lifecycle state, nonce, UTC timestamp, certificate chain, and monotonic counter.
**Output:** attested/rejected result, evidence digest, firmware digest, lifecycle state, reasons, and counter.
**Algorithm:** canonicalise all evidence except the signature; calculate HMAC-SHA-256 with a protected verifier key; compare in constant time; validate lifecycle allowlist, digest syntax, approved firmware digest, timestamp, and anti-rollback counter.
**Failure modes:** invalid signature, untrusted firmware, illegal lifecycle state, malformed digest, stale/invalid counter, missing evidence, missing protected key. Every failure stops the pipeline.

## ChipWhisperer
**Purpose:** detect physical deviations and hardware-Trojan side-channel signatures from power/EM/timing traces.
**Input:** candidate and trusted-reference JSON traces with numeric samples.
**Output:** anomaly score, threshold, SHA-256 trace digest, correlation, RMS, peak-to-peak, crest factor, spectral centroid, high-frequency ratio, reasons.
**Algorithm:** validate samples; z-normalise; cross-correlate over bounded shifts; align traces; compute descriptive and discrete-frequency features; fuse correlation loss, high-frequency energy, and distribution deviation into a bounded anomaly score.
**Failure modes:** short/non-numeric/non-finite trace, low correlation, score over threshold, missing reference, malformed JSON.

## Yosys
**Purpose:** synthesise authorised RTL, generate a canonical netlist, and enforce structural hardware-security rules.
**Input:** SystemVerilog/Verilog file and explicit top module.
**Output:** RTL/netlist/log digests, cell/wire/memory metrics, cell-type distribution, policy verdict.
**Algorithm:** run isolated Yosys commands (`read_verilog`, `hierarchy -check`, `proc`, `opt`, `check`, `write_json`, `stat -json`); parse statistics; enforce configured maxima and cell allow/deny requirements.
**Failure modes:** missing executable, syntax error, unresolved top, synthesis/check failure, missing output, forbidden cells, resource-limit violation.

## Verilator
**Purpose:** compile and execute an assertion-enabled behavioural simulation against an authorised testbench.
**Input:** RTL, testbench, and top module.
**Output:** pass/fail, warnings, assertion count, cycle count, output/RTL/testbench digests.
**Algorithm:** use `verilator --binary --timing --assert`; run the isolated binary; reject non-zero builds/runs, assertion/fatal markers, and absence of the explicit `SEMISURE_PASS` marker.
**Failure modes:** unavailable executable, compile failure, timeout, assertion failure, fatal simulation, missing pass marker, malformed testbench.

## SBOM
**Purpose:** produce a deterministic software/firmware/IP inventory for provenance and compliance.
**Input:** chip ID, actual artifact files, optional supplier/version metadata.
**Output:** CycloneDX 1.5 JSON, serial number, component count, component SHA-256 hashes, document digest.
**Algorithm:** resolve each artifact, hash content in chunks, sort components, construct CycloneDX metadata, hash the canonical document, and atomically persist it.
**Failure modes:** missing/unreadable artifact, empty component set, unsupported format, forbidden licence, write failure.

## Digital Twin
**Purpose:** bind the physical chip and PUF identity to approved design, netlist, firmware, SBOM, supplier, lot, custody, and lifecycle records.
**Input:** immutable JSON twin and current scan evidence digests.
**Output:** verified/mismatch result, twin digest, field-level mismatch map.
**Algorithm:** atomically store one JSON record per safe identifier; compare chip ID and all security digests exactly; hash the canonical twin for provenance.
**Failure modes:** missing twin, malformed twin, path traversal attempt, PUF/design/netlist/firmware/SBOM mismatch.

## Backend Integration
`HardwareSecurityPipeline` executes OpenTitan → ChipWhisperer → Yosys → Verilator → SBOM → Digital Twin. It persists `stage.started`, `stage.completed`, or `stage.failed` records in the hash-chained JSON event store and publishes only persisted records through Socket.IO. Any exception or negative verdict returns `QUARANTINED`; later AI, compliance, blockchain, and deployment stages must not run.
