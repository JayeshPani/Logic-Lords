#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LSTM_MODEL="${ROOT_DIR}/data-platform/ml/models/lstm_failure_predictor.pt"
IF_MODEL="${ROOT_DIR}/data-platform/ml/models/isolation_forest.joblib"
IF_META="${ROOT_DIR}/data-platform/ml/models/isolation_forest.meta.json"

if [ ! -f "${LSTM_MODEL}" ]; then
  echo "Missing LSTM model: ${LSTM_MODEL}" >&2
  exit 1
fi
if [ ! -f "${IF_MODEL}" ]; then
  echo "Missing Isolation Forest model: ${IF_MODEL}" >&2
  exit 1
fi
if [ ! -f "${IF_META}" ]; then
  echo "Missing Isolation Forest meta: ${IF_META}" >&2
  exit 1
fi

export FORECAST_PREDICTOR_MODE=torch
export FORECAST_TORCH_MODEL_PATH="${LSTM_MODEL}"
export ANOMALY_PRETRAINED_MODEL_PATH="${IF_MODEL}"
export ANOMALY_PRETRAINED_META_PATH="${IF_META}"

echo "Trained-model runtime env exported:"
echo "  FORECAST_PREDICTOR_MODE=${FORECAST_PREDICTOR_MODE}"
echo "  FORECAST_TORCH_MODEL_PATH=${FORECAST_TORCH_MODEL_PATH}"
echo "  ANOMALY_PRETRAINED_MODEL_PATH=${ANOMALY_PRETRAINED_MODEL_PATH}"
echo "  ANOMALY_PRETRAINED_META_PATH=${ANOMALY_PRETRAINED_META_PATH}"
