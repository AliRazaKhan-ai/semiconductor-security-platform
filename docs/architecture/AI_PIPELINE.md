# Production AI Pipeline

## Feature extraction
The extractor combines three evidence domains. Side-channel traces are validated, resampled to 256 time steps, standardized per channel, and summarized through RMS, peak-to-peak amplitude, crest factor, moments, spectral entropy, and timing jitter. Yosys and Verilator results become bounded structural features. Supplier, custody, SBOM, PUF, OpenTitan, and threat-intelligence values become provenance features. A fixed 34-feature schema, v2.1, prevents silent training and inference drift: 16 physical, 10 design and 8 supply-chain features. The 32-feature schema was v1.0 and is retired.

## TensorFlow CNN
A one-dimensional CNN is selected for known-pattern classification because power, electromagnetic, and timing measurements are synchronized temporal signals. Local convolution kernels learn trigger bursts, periodic modulation, and correlated deviations without requiring hand-selected time locations. The model returns CLEAN, TROJAN, or TAMPERED probabilities. Confidence combines top probability, class margin, and normalized entropy; uncertain results are labelled INDETERMINATE.

## PyTorch autoencoder
The autoencoder is trained only on accepted clean feature vectors. It compresses and reconstructs the normal operating manifold. Unknown attacks, process anomalies, and unseen Trojan families produce elevated reconstruction error. The anomaly threshold is the 99.5th percentile of clean validation errors. A logistic transformation maps distance from the threshold to an anomaly probability.

## Scikit-learn risk engine
A calibrated random forest combines the 34 normalized features with CNN score/confidence and anomaly score/confidence. Trees capture non-linear interactions between physical, design, and supply-chain evidence. Probability calibration improves the operational meaning of the risk score. Mandatory controls are applied after the learned model: failed PUF, OpenTitan, digital-twin, or compliance checks force critical risk and block deployment.

## Scores and classification
Risk score is a bounded fusion of calibrated model risk, CNN threat probability, anomaly probability, and mandatory policy overrides. Confidence is based on model certainty, risk separation from 0.5, and evidence quality. Final classes are CLEAN, SUSPICIOUS, or COMPROMISED. Recommendations are PROCEED_TO_COMPLIANCE, MANUAL_REVIEW, or BLOCK.

## Failure modes
Missing or malformed traces, feature-schema mismatch, invalid model digest, unavailable framework, non-finite output, missing mandatory evidence, and model loading errors all fail closed. No missing model result can be interpreted as a safe chip.

## Measured performance

Risk engine on the held-out test split: ROC-AUC 0.9911, accuracy 0.9493,
precision and recall 0.93 to 0.96. TensorFlow classifier accuracy 0.7907; the CNN
receives sequences that extract_physical z-normalises per channel, which removes
the amplitude the Trojan signal is strongest in, so it classifies on waveform
shape alone while the risk engine sees the amplitude features directly.

All three artefacts share one dataset digest and one split digest, checked by
scripts/ai/registry.py. Corpus 769b1e1c, split 802990b4.

The corpus is synthetic and holds two netlist profiles: the 8-cell reference and
the 27-cell controlled Trojan. No mean shift is applied to any column; separation
derives from that structural difference propagated through the production trace
synthesiser and the production feature extractors. Any metric obtained on it
measures separability between those two designs, not detector performance on real
silicon.

Drift monitoring compares each normalised vector against the fitted training
support and reports without deciding. Observations accumulate in
evidence/ai/drift/.

