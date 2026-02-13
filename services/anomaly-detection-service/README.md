# Anomaly Detection Service

Detects structural anomalies using Isolation Forest configuration with heuristic fallback.

## Responsibilities

- Evaluate abnormal structural behavior using strain, vibration, temperature, humidity.
- Expose `anomaly_score` and `anomaly_flag`.
- Use Isolation Forest parameters from `AI_INTEGRATION.md`:
  - `n_estimators=100`
  - `contamination=0.02`
  - `random_state=42`

## API

- `GET /health`
- `POST /detect`

## Use Pretrained Model

```bash
export ANOMALY_PRETRAINED_MODEL_PATH=data-platform/ml/models/isolation_forest.joblib
export ANOMALY_PRETRAINED_META_PATH=data-platform/ml/models/isolation_forest.meta.json
```

## Run

```bash
cd services/anomaly-detection-service
python3 -m uvicorn src.main:app --reload --port 8105
```
