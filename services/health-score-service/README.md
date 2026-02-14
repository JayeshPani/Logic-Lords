# Health Score Service

Formats final AI pipeline outputs into the canonical response expected by the dashboard and downstream systems.

## Specification Alignment

Expected output format from `AI_INTEGRATION.md`:

```json
{
  "health_score": 0.73,
  "failure_probability_72h": 0.65,
  "anomaly_flag": 0,
  "risk_level": "High",
  "timestamp": "ISO8601"
}
```

## API

- `GET /health`
- `GET /metrics`
- `POST /compose`

## Run

```bash
cd services/health-score-service
python3 -m uvicorn src.main:app --reload --port 8103
```

## Environment

- `HEALTH_SCORE_LOG_LEVEL` (default: `INFO`)
- `HEALTH_SCORE_METRICS_ENABLED` (default: `true`)
- `HEALTH_SCORE_EVENT_PRODUCED_BY` (default: `services/health-score-service`)

## Module-8 Validation

```bash
make module8-check
```

## Notes

- `/compose` emits structured JSON logs with trace-aware fields.
- `asset.risk.computed` event payload shape is built on each compose call and validated by contract tests.
- `/metrics` exposes in-memory Prometheus-style counters and latency metrics for compose traffic.
