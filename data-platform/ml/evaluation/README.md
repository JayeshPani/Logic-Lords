# ML Evaluation Layer

Offline evaluation and backtesting scripts for trained model artifacts.

## Scripts

- `evaluate_lstm_torch.py`:
  - Loads `lstm_failure_predictor.pt`
  - Rebuilds 48h->72h sequences
  - Computes regression + thresholded risk metrics
  - Computes proxy-event threshold sweep and recommended threshold
  - Supports event-aware split strategy to enforce proxy events in val/test when feasible
  - Writes backtest predictions CSV

- `evaluate_isolation_forest.py`:
  - Loads `isolation_forest.joblib` + meta calibration
  - Scores canonical records across datasets
  - Computes anomaly-rate diagnostics, proxy-label metrics, and threshold sweep

- `evaluate_all_models.py`:
  - Runs both evaluations and writes combined summary

## Run

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py
```

Optional calibration controls:

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py --lstm-calibration-split all --anomaly-threshold 0.65
```

Split-strategy controls:

```bash
python3 data-platform/ml/evaluation/evaluate_all_models.py \
  --lstm-split-strategy event_aware \
  --lstm-min-proxy-events-val 1 \
  --lstm-min-proxy-events-test 1
```

## Outputs

- `data-platform/ml/reports/evaluation_summary.json`
- `data-platform/ml/reports/lstm_backtest_report.json`
- `data-platform/ml/reports/isolation_forest_evaluation_report.json`
- `data-platform/ml/reports/lstm_backtest_predictions.csv`

Recommended operating thresholds are included in:
- `proxy_event_recommended_threshold` (LSTM report)
- `proxy_recommended_threshold_total` (Isolation Forest report)
