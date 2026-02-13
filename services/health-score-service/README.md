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
- `POST /compose`

## Run

```bash
cd services/health-score-service
python3 -m uvicorn src.main:app --reload --port 8103
```
