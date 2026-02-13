# AI Integration Alignment

This file maps `AI_INTEGRATION.md` requirements to implementation modules.

## 1) Data Pipeline

- Raw inputs accepted by forecast service schema:
  - `services/lstm-forecast-service/src/lstm_forecast/schemas.py`
- Normalization to `[0,1]`:
  - `services/lstm-forecast-service/src/lstm_forecast/preprocessing.py`

## 2) LSTM 72h Failure Prediction

- Inference contract and 48h window:
  - `services/lstm-forecast-service/src/lstm_forecast/routes.py`
  - `services/lstm-forecast-service/src/lstm_forecast/preprocessing.py`
- Architecture spec endpoint:
  - `GET /model/spec`
- Trained Torch predictor runtime:
  - `services/lstm-forecast-service/src/lstm_forecast/config.py`
  - `services/lstm-forecast-service/src/lstm_forecast/predictor.py`
- Backtesting/evaluation:
  - `data-platform/ml/evaluation/evaluate_lstm_torch.py`

## 3) Isolation Forest Anomaly Detection

- Dedicated service:
  - `services/anomaly-detection-service`
- Configured with:
  - `n_estimators=100`
  - `contamination=0.02`
  - `random_state=42`
- Pretrained model runtime:
  - `services/anomaly-detection-service/src/anomaly_detection/config.py`
  - `services/anomaly-detection-service/src/anomaly_detection/engine.py`
- Heuristic fallback remains available only when pretrained/sklearn runtime is unavailable.
- Evaluation diagnostics:
  - `data-platform/ml/evaluation/evaluate_isolation_forest.py`

## 4) Fuzzy Logic (Mamdani + Centroid)

- Engine:
  - `services/fuzzy-inference-service/src/fuzzy_inference/engine.py`
- Membership functions match spec variables.
- Rule base includes 15 rules.
- Defuzzification uses centroid sampling.

## 5) Final Output Format

- Formatter service:
  - `services/health-score-service`
- Output payload:
  - `health_score`
  - `failure_probability_72h`
  - `anomaly_flag`
  - `risk_level`
  - `timestamp`

## 6) Contracts

- ML contracts in `contracts/ml/*.schema.json` updated to match this architecture.
- End-to-end contract assertions (ML + event envelopes):
  - `scripts/validate_ai_contracts.py`
