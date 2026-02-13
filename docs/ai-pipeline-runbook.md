# AI Pipeline Runbook

This runbook executes the full AI flow and model-evaluation steps.

1. Forecast (`lstm-forecast-service`) -> `failure_probability_72h`
2. Anomaly detection (`anomaly-detection-service`) -> `anomaly_score`, `anomaly_flag`
3. Fuzzy inference (`fuzzy-inference-service`) -> `final_risk_score`
4. Final output formatting (`health-score-service`) -> expected dashboard payload

## Local Runner

```bash
./scripts/ai_pipeline_local.py
```

## Train Models

```bash
python3 data-platform/ml/training/train_all_models.py
```

## Activate Trained Runtime (Step 1)

```bash
source ./scripts/activate_trained_runtime.sh
python3 ./scripts/verify_trained_runtime.py
```

## Evaluate Trained Models (Step 2)

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py
```

Use explicit calibration split for LSTM threshold recommendation (default is `all`):

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py --lstm-calibration-split all
```

Use event-aware split strategy for sparse-event datasets:

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py \
  --lstm-split-strategy event_aware \
  --lstm-min-proxy-events-val 1 \
  --lstm-min-proxy-events-test 1
```

Primary outputs:

- `data-platform/ml/reports/evaluation_summary.json`
- `data-platform/ml/reports/lstm_backtest_report.json`
- `data-platform/ml/reports/isolation_forest_evaluation_report.json`
- `data-platform/ml/reports/lstm_backtest_predictions.csv`

Calibration outputs inside reports:

- LSTM: `proxy_event_recommended_threshold`
- Isolation Forest: `proxy_recommended_threshold_total`

## Validate Pipeline Contracts (Step 3)

```bash
python3 scripts/validate_ai_contracts.py --fail-on-invalid
```

Primary output:

- `data-platform/ml/reports/ai_contract_validation_report.json`

## One-Command Step 2 + Step 3

```bash
make ai-check
```

This runs:

- step-2 model evaluation/backtesting
- step-3 contract validation
- integration test `tests/integration/test_ai_contract_validation.py`

## Run Pipeline With Trained Models

```bash
export FORECAST_PREDICTOR_MODE=torch
export FORECAST_TORCH_MODEL_PATH=data-platform/ml/models/lstm_failure_predictor.pt
export ANOMALY_PRETRAINED_MODEL_PATH=data-platform/ml/models/isolation_forest.joblib
export ANOMALY_PRETRAINED_META_PATH=data-platform/ml/models/isolation_forest.meta.json

./scripts/ai_pipeline_local.py --dataset data-platform/ml/datasets/bridge_digital_twin_dataset.csv --kind digital_twin --limit 500
```

The script prints output in the expected shape:

```json
{
  "health_score": 0.73,
  "failure_probability_72h": 0.65,
  "anomaly_flag": 0,
  "risk_level": "High",
  "timestamp": "ISO8601"
}
```

## Notes

- Training and evaluation are offline steps; API services do inference only.
- Forecast service defaults to Torch predictor mode with trained artifact paths.
- Anomaly service defaults to pretrained Isolation Forest artifact paths.
