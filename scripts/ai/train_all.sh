#!/usr/bin/env bash
set -euo pipefail

DATASET="${1:-data/training/semiconductor_ai.npz}"
SIGNALS="${2:-data/training/model_signals.npz}"
SPLIT="${3:-data/training/semiconductor_ai.split.json}"
NORMALIZER="models/manifests/feature_normalizer.json"
SEED="${4:-42}"
LINEAGE="${5:-models/manifests/ai_training_lineage.json}"

python scripts/ai/dataset.py \
  --dataset "$DATASET" \
  --output "$SPLIT" \
  --seed "$SEED"

python scripts/ai/train_normalizer.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --output "$NORMALIZER"

python scripts/ai/train_tensorflow_cnn.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --output models/tensorflow/trojan_cnn.keras \
  --seed "$SEED"

python scripts/ai/train_pytorch_autoencoder.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --normalizer "$NORMALIZER" \
  --output models/pytorch/anomaly_autoencoder.pt \
  --seed "$SEED"

python scripts/ai/generate_model_signals.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --normalizer "$NORMALIZER" \
  --tensorflow-model models/tensorflow/trojan_cnn.keras \
  --pytorch-model models/pytorch/anomaly_autoencoder.pt \
  --output "$SIGNALS"

python scripts/ai/train_risk_engine.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --normalizer "$NORMALIZER" \
  --model-signals "$SIGNALS" \
  --output models/sklearn/risk_engine.joblib \
  --seed "$SEED"

python scripts/ai/write_lineage_manifest.py \
  --dataset "$DATASET" \
  --split "$SPLIT" \
  --normalizer "$NORMALIZER" \
  --model-signals "$SIGNALS" \
  --tensorflow-model models/tensorflow/trojan_cnn.keras \
  --tensorflow-metrics models/tensorflow/trojan_cnn.metrics.json \
  --pytorch-model models/pytorch/anomaly_autoencoder.pt \
  --pytorch-metrics models/pytorch/anomaly_autoencoder.metrics.json \
  --risk-model models/sklearn/risk_engine.joblib \
  --risk-metrics models/sklearn/risk_engine.metrics.json \
  --seed "$SEED" \
  --output "$LINEAGE"
