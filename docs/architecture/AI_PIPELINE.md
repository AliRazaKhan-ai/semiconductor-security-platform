# Production AI Pipeline

## Feature extraction
The extractor combines three evidence domains. Side-channel traces are validated, resampled to 256 time steps, standardized per channel, and summarized through RMS, peak-to-peak amplitude, crest factor, moments, spectral entropy, and timing jitter. Yosys and Verilator results become bounded structural features. Supplier, custody, SBOM, PUF, OpenTitan, and threat-intelligence values become provenance features. A fixed 32-feature schema prevents silent training/inference drift.

## TensorFlow CNN
A one-dimensional CNN is selected for known-pattern classification because power, electromagnetic, and timing measurements are synchronized temporal signals. Local convolution kernels learn trigger bursts, periodic modulation, and correlated deviations without requiring hand-selected time locations. The model returns CLEAN, TROJAN, or TAMPERED probabilities. Confidence combines top probability, class margin, and normalized entropy; uncertain results are labelled INDETERMINATE.

## PyTorch autoencoder
The autoencoder is trained only on accepted clean feature vectors. It compresses and reconstructs the normal operating manifold. Unknown attacks, process anomalies, and unseen Trojan families produce elevated reconstruction error. The anomaly threshold is the 99.5th percentile of clean validation errors. A logistic transformation maps distance from the threshold to an anomaly probability.

## Scikit-learn risk engine
A calibrated random forest combines the 32 normalized features with CNN score/confidence and anomaly score/confidence. Trees capture non-linear interactions between physical, design, and supply-chain evidence. Probability calibration improves the operational meaning of the risk score. Mandatory controls are applied after the learned model: failed PUF, OpenTitan, digital-twin, or compliance checks force critical risk and block deployment.

## Scores and classification
Risk score is a bounded fusion of calibrated model risk, CNN threat probability, anomaly probability, and mandatory policy overrides. Confidence is based on model certainty, risk separation from 0.5, and evidence quality. Final classes are CLEAN, SUSPICIOUS, or COMPROMISED. Recommendations are PROCEED_TO_COMPLIANCE, MANUAL_REVIEW, or BLOCK.

## Failure modes
Missing or malformed traces, feature-schema mismatch, invalid model digest, unavailable framework, non-finite output, missing mandatory evidence, and model loading errors all fail closed. No missing model result can be interpreted as a safe chip.
