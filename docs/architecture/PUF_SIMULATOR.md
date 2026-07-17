# Production Hybrid PUF Simulator

## Purpose

This module implements the PUF authentication stage required by the semiconductor supply-chain security platform. It combines a Ring Oscillator PUF, an Arbiter Delay-Chain PUF, environment-dependent drift, a device-specific noise signature, one-time challenges, protected enrollment templates, hashed identity, authentication, and anti-cloning controls.

It is a high-fidelity deterministic simulator for development, testing, demonstration, and pipeline validation. A software simulator cannot create the unclonable manufacturing variation of real silicon; production deployment must connect the same verifier contract to physical PUF hardware or an OpenTitan-backed secure element.

## 1. Device process-variation derivation

Each simulated chip receives a 256-bit device secret derived from the server-held PUF master secret using HMAC-SHA-256 and the chip identifier. The device secret is never written to JSON. HMAC counter-mode deterministic random generation derives independent populations for oscillator frequencies, delay cells, temperature coefficients, voltage coefficients, and noise characteristics.

The same device secret recreates the same physical device model. A different secret creates statistically independent process variation, which is the basis of clone rejection.

## 2. Ring Oscillator algorithm

The simulator creates 96 ring oscillators. For oscillator `i`, the fabrication frequency is:

`f_process(i) = f_nominal × (1 + Gaussian(0, process_sigma_ppm / 10^6))`

A challenge selects 48 unique oscillator pairs. During a response, each oscillator is adjusted for voltage, temperature, age, correlated noise, flicker noise, white noise, and counter jitter:

`f(i) = f_process(i) × (V / V_nominal)^alpha_i × temperature_factor_i × aging_factor × noise_factor`

The measurement count is:

`count(i) = f(i) × measurement_window + counter_jitter`

For pair `(a, b)`, the response bit is `1` when `count(a) >= count(b)`, otherwise `0`. The normalised count difference becomes the confidence margin. Pairs with small margins naturally show lower reliability under drift and are removed by enrollment masking.

## 3. Arbiter Delay-Chain algorithm

The simulator creates 64 switching stages. Every stage has four independently varied propagation paths: upper-straight, lower-to-upper cross, upper-to-lower cross, and lower-straight. Each of the 48 delay response bits uses a separate 64-bit switch pattern.

For challenge bit `0`, both racing signals travel straight. For challenge bit `1`, the paths cross. Path delays accumulate through all stages. Each cell is adjusted for voltage, temperature, age, common noise, white delay noise, and final arbiter jitter.

The bit is `1` when the upper signal arrives first or at the same time; otherwise it is `0`. The absolute final race difference divided by nominal total path delay is the delay margin.

This is physically interpretable: the response is the sign of a race whose outcome depends on manufacturing mismatch distributed across the complete path.

## 4. Voltage drift

Ring oscillator frequency increases approximately with a configurable power of supply voltage:

`frequency_voltage_factor = (V / V_nominal)^alpha`

CMOS propagation delay moves in the opposite direction:

`delay_voltage_factor = (V_nominal / V)^beta`

Per-device coefficient variation prevents voltage drift from cancelling perfectly between competing structures. Authentication accepts only the configured 0.85 V to 1.15 V operating range.

## 5. Temperature drift

The ring model applies a negative parts-per-million frequency coefficient per degree Celsius. The delay model applies a positive parts-per-million delay coefficient per degree Celsius. Each oscillator and delay path receives a small independent coefficient variation.

Enrollment samples nominal, cold, hot, low-voltage, and high-voltage corners. Only bits that remain stable across those corners are used for authentication.

## 6. Aging drift

Configurable coefficients gradually reduce oscillator frequency and increase path delay as simulated operating hours increase. The environment penalty includes age so that extreme unmodelled aging fails closed rather than silently producing an approval.

## 7. Noise signature algorithm

Every device receives an eight-dimensional latent noise fingerprint. Each dimension combines a device-specific baseline, device-specific temperature sensitivity, device-specific voltage sensitivity, aging contribution, and small run-time noise.

Enrollment calculates the mean and sample standard deviation of the vector across environmental corners. Authentication calculates the root-mean-square standardised distance:

`distance = sqrt(mean(((observed - reference) / scale)^2))`

This supplements response-bit comparison. A clone may occasionally match some response bits, but it must also match the enrolled device's multi-dimensional noise behaviour.

## 8. Challenge generation

The challenge issuer generates a cryptographically random 256-bit nonce. An HMAC counter-mode generator converts the nonce into unique ring pairs and unique delay-chain patterns. The challenge contains:

- Challenge identifier and sequence
- Physical stimulus definition
- Issue and expiry timestamps
- Stimulus SHA-256 digest
- Complete challenge SHA-256 digest
- HMAC issuer tag

The issuer tag prevents a terminal from altering a challenge and recomputing only an unkeyed hash.

## 9. Response generation

A response contains 48 Ring Oscillator bits followed by 48 Delay-Chain bits. Nine repeated measurements are taken by default. Every bit is majority-voted, and its reliability is the majority fraction. The response includes per-bit margins, overall reliability, environment, noise signature, a fresh response nonce, and a SHA-256 integrity digest.

## 10. Enrollment algorithm

Sixteen one-time challenges are generated for each chip. Every challenge is measured at five environmental corners, with eleven repeated measurements at each corner.

For every bit:

1. Majority vote responses across corners.
2. Combine cross-corner stability with within-response reliability.
3. Retain the bit only when reliability is at least 0.82.
4. Require at least 70 percent of the total response to remain stable.
5. Reject excessively biased stable responses.

The complete reference response is not stored in clear text. It is sealed using an HMAC-derived keystream and protected by an HMAC authentication tag. A separate HMAC commitment detects template substitution.

## 11. Hashed identity

The chip identity is:

`SHA-256(device_id || configuration_fingerprint || ordered_response_commitments)`

The identity binds the device name, exact PUF model, and all enrolled challenge-response templates. The full enrollment profile is signed with HMAC-SHA-256, so changing thresholds, masks, challenges, or identity invalidates the profile.

## 12. Authentication algorithm

The verifier performs these checks in order:

1. Verify profile HMAC signature.
2. Verify configuration fingerprint.
3. Verify challenge stimulus digest, challenge digest, HMAC issuer tag, timestamps, and expiry.
4. Verify response digest and challenge binding.
5. Confirm the challenge belongs to the enrolled challenge bank.
6. Atomically consume the one-time challenge in the JSONL anti-replay ledger.
7. Unseal and authenticate the reference response.
8. Compare only stable bits using masked Hamming distance.
9. Check selected-bit reliability.
10. Compare the noise signature.
11. Check environmental range and penalty.
12. Return authenticated or fail closed with explicit reasons.

The configured maximum masked Hamming ratio is 0.14. A response is never considered safe because a model or dependency is unavailable.

## 13. Anti-cloning controls

Anti-cloning uses multiple independent controls:

- Different device secrets generate independent process variation.
- Hybrid frequency and delay responses increase modelling difficulty.
- Stable-bit masked Hamming distance rejects a different physical model.
- Device-specific noise distance rejects statistical impersonation.
- Challenges are signed, short-lived, issued once, and consumed once.
- The append-only JSONL challenge ledger detects replay.
- Enrollment references are sealed and committed, not stored as clear CRPs.
- The challenge bank is finite; exhaustion requires controlled re-enrollment.

A clone attempt normally approaches an inter-device Hamming ratio near 0.5, while a genuine response remains close to its enrolled template.

## 14. Pipeline behaviour

The PUF stage accepts only terminal evidence containing a challenge and response. It writes `stage.started`, then either `stage.completed` or `stage.failed` to the hash-chained JSON Event Store and publishes the durable event to SocketIO. Failure sets `stop_pipeline: true`; OpenTitan and all later stages must not run.

## 15. Secret handling

Set `SEMISURE_PUF_MASTER_SECRET` to at least 32 bytes. Accepted forms are plain UTF-8, `hex:...`, or `base64:...`. The secret must be delivered through the runtime secret-management mechanism and must never be committed to JSON, logs, screenshots, or source control.
