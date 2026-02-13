# Fuzzy Inference Service

Mamdani fuzzy inference engine for interpretable infrastructure risk scoring.

## Specification Alignment

- Inference type: Mamdani
- Defuzzification: Centroid
- Inputs: strain, vibration, temperature, rainfall, traffic, failure probability, anomaly score
- Output: `final_risk_score` in `[0,1]` and `risk_level`
- Rule base: 15 rules (minimum required was 10)

## API

- `GET /health`
- `POST /infer`
- `GET /metrics`

## Run

```bash
cd services/fuzzy-inference-service
python3 -m uvicorn src.main:app --reload --port 8102
```

## Environment

- `FUZZY_LOG_LEVEL` (default: `INFO`)
- `FUZZY_CENTROID_RESOLUTION` (default: `401`)
- `FUZZY_ANOMALY_FLAG_THRESHOLD` (default: `0.7`)
- `FUZZY_EVENT_PRODUCED_BY` (default: `services/fuzzy-inference-service`)

## Module-5 Validation

```bash
make module5-check
```

## Notes

- `/infer` emits structured JSON logs with trace-aware fields.
- `asset.risk.computed` event payload shape is built on each inference and validated by contract tests.
- `/metrics` exposes in-memory Prometheus-style counters and latency metrics for inference traffic.
