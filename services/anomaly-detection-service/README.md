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
- `GET /metrics`
- `POST /detect`

## Use Pretrained Model

```bash
export ANOMALY_PRETRAINED_MODEL_PATH=data-platform/ml/models/isolation_forest.joblib
export ANOMALY_PRETRAINED_META_PATH=data-platform/ml/models/isolation_forest.meta.json
```

## Environment

- `ANOMALY_LOG_LEVEL` (default: `INFO`)
- `ANOMALY_METRICS_ENABLED` (default: `true`)
- `ANOMALY_EVENT_PRODUCED_BY` (default: `services/anomaly-detection-service`)
- `ANOMALY_FALLBACK_TO_HEURISTIC_ON_STARTUP_ERROR` (default: `true`)
- `ANOMALY_MIN_MODEL_CONFIDENCE` (default: `0.0`)

## Run

```bash
cd services/anomaly-detection-service
python3 -m uvicorn src.main:app --reload --port 8105
```

## Module-7 Validation

```bash
make module7-check
```

## Notes

- `/detect` emits structured JSON logs with trace-aware fields.
- `asset.anomaly.detected` event payload shape is built on each detect call and validated by contract tests.
- `/metrics` exposes in-memory Prometheus-style counters and latency metrics for anomaly traffic.
