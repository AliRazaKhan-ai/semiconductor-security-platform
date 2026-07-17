#!/usr/bin/env bash
set -euo pipefail
DATASET="${1:-data/training/semiconductor_ai.npz}"
SIGNALS="${2:-data/training/model_signals.npz}"
python scripts/ai/train_normalizer.py --dataset "$DATASET" --output models/manifests/feature_normalizer.json
python scripts/ai/train_tensorflow_cnn.py --dataset "$DATASET" --output models/tensorflow/trojan_cnn.keras
python scripts/ai/train_pytorch_autoencoder.py --dataset "$DATASET" --output models/pytorch/anomaly_autoencoder.pt
python scripts/ai/train_risk_engine.py --dataset "$DATASET" --model-signals "$SIGNALS" --output models/sklearn/risk_engine.joblib
