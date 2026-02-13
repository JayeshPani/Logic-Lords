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

## Run

```bash
cd services/fuzzy-inference-service
python3 -m uvicorn src.main:app --reload --port 8102
```
