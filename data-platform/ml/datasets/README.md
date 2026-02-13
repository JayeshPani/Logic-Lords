# Dataset Mapping Guide

Datasets currently available at project root:

- `bridge_dataset.csv`
- `bridge_digital_twin_dataset.csv`
- `merged_dataset_BearingTest_2.csv`

## Canonical AI Input Format

All datasets are adapted to:

- `strain_value`
- `vibration_rms`
- `temperature`
- `humidity`
- `traffic_density` (optional)
- `rainfall_intensity` (optional)
- `timestamp`

## Adapter Utilities

- `scripts/dataset_adapters.py`
- `scripts/prepare_ai_dataset.py`

## Prepare Dataset Example

```bash
./scripts/prepare_ai_dataset.py \
  --dataset bridge_digital_twin_dataset.csv \
  --kind digital_twin \
  --output data-platform/ml/datasets/prepared_digital_twin.jsonl
```

## Run AI Pipeline with Dataset

```bash
./scripts/ai_pipeline_local.py \
  --dataset bridge_digital_twin_dataset.csv \
  --kind digital_twin \
  --limit 500
```

No training is performed by these scripts.

## Train Models

```bash
python3 data-platform/ml/training/train_all_models.py
```

This produces:

- `data-platform/ml/models/lstm_failure_predictor.pt`
- `data-platform/ml/models/lstm_failure_predictor.meta.json`
- `data-platform/ml/models/isolation_forest.joblib`
- `data-platform/ml/models/isolation_forest.meta.json`
