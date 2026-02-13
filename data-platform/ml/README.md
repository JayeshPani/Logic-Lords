# ML Data Layer

## Purpose
Dataset curation and model artifact lifecycle support for AI services.

## Components
- `datasets/`: training and evaluation source datasets.
- `training/`: offline model training scripts for LSTM and Isolation Forest.
- `models/`: serialized model artifacts and training metadata.
- `evaluation/`: offline backtesting and evaluation scripts.
- `reports/`: generated evaluation reports and prediction traces.

## Quick Commands

```bash
# Train artifacts
python3 data-platform/ml/training/train_all_models.py

# Step-2 evaluation/backtesting
python3 data-platform/ml/evaluation/evaluate_all_models.py

# Step-3 contract assertions
python3 scripts/validate_ai_contracts.py --fail-on-invalid

# Step-2 + Step-3 + integration check
make ai-check
```

Evaluation reports include threshold-calibration recommendations for:
- LSTM risk probability cutoff
- Isolation Forest anomaly cutoff
- Event-aware split metadata for sparse incident labels
