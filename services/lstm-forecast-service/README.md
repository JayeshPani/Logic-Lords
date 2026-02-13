# LSTM Forecast Service

72-hour failure prediction service aligned with `AI_INTEGRATION.md`.

## Specification Alignment

- Input pipeline uses raw sensor records:
  - `strain_value`
  - `vibration_rms`
  - `temperature`
  - `humidity`
  - optional: `traffic_density`, `rainfall_intensity`
  - `timestamp`
- Uses last 48-hour window.
- Normalizes inputs to `[0,1]` before inference.
- Supports model architecture contract:
  - Input
  - LSTM(64, return_sequences=True)
  - Dropout(0.2)
  - LSTM(32)
  - Dense(16, relu)
  - Dense(1, sigmoid)

Current mode: `surrogate` (no training required).
Optional mode: `keras` with pre-trained `.h5` model loading.
Optional mode: `torch` with pre-trained `.pt` model loading.

## API

- `GET /health`
- `GET /metrics`
- `GET /model/spec`
- `POST /forecast`

## Run

```bash
cd services/lstm-forecast-service
python3 -m uvicorn src.main:app --reload --port 8104
```

## Use Trained Torch Model

```bash
export FORECAST_PREDICTOR_MODE=torch
export FORECAST_TORCH_MODEL_PATH=data-platform/ml/models/lstm_failure_predictor.pt
export FORECAST_TORCH_META_PATH=data-platform/ml/models/lstm_failure_predictor.meta.json
```

## Environment

- `FORECAST_LOG_LEVEL` (default: `INFO`)
- `FORECAST_METRICS_ENABLED` (default: `true`)
- `FORECAST_EVENT_PRODUCED_BY` (default: `services/lstm-forecast-service`)
- `FORECAST_FALLBACK_TO_SURROGATE_ON_STARTUP_ERROR` (default: `true`)
- `FORECAST_MIN_MODEL_CONFIDENCE` (default: `0.0`)

## Module-6 Validation

```bash
make module6-check
```

## Notes

- `/forecast` emits structured JSON logs with trace-aware fields.
- `asset.failure.predicted` event payload shape is built on each forecast and validated by contract tests.
- `/metrics` exposes in-memory Prometheus-style counters and latency metrics for forecast traffic.
