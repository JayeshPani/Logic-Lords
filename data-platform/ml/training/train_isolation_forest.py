#!/usr/bin/env python3
"""Train Isolation Forest anomaly model for InfraGuard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.append(str(SCRIPTS_DIR))
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))

from dataset_adapters import load_canonical_records, records_to_dicts
from lstm_forecast.config import Settings as ForecastSettings
from lstm_forecast.preprocessing import SensorNormalizer

from sklearn.ensemble import IsolationForest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Isolation Forest model")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=[
            "data-platform/ml/datasets/bridge_dataset.csv",
            "data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
            "data-platform/ml/datasets/merged_dataset_BearingTest_2.csv",
        ],
    )
    parser.add_argument("--limit-per-dataset", type=int, default=None)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--contamination", type=float, default=0.02)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--model-out",
        default="data-platform/ml/models/isolation_forest.joblib",
    )
    parser.add_argument(
        "--meta-out",
        default="data-platform/ml/models/isolation_forest.meta.json",
    )
    return parser.parse_args()


def collect_training_matrix(dataset_paths: list[str], limit: int | None) -> tuple[np.ndarray, list[dict]]:
    normalizer = SensorNormalizer(ForecastSettings())

    rows = []
    summaries = []

    for dataset in dataset_paths:
        records, summary = load_canonical_records(dataset, dataset_kind="auto", limit=limit)
        rows.extend(records_to_dicts(records))
        summaries.append(
            {
                "dataset": summary.dataset_path,
                "kind": summary.dataset_kind,
                "rows_loaded": summary.rows_loaded,
            }
        )

    if not rows:
        raise ValueError("No records loaded for anomaly training")

    features = []
    for row in rows:
        normalized = normalizer.normalize_record(row)
        features.append(
            [
                normalized["strain"],
                normalized["vibration"],
                normalized["temperature"],
                normalized["humidity"],
            ]
        )

    return np.asarray(features, dtype=np.float32), summaries


def main() -> None:
    args = parse_args()

    x, summaries = collect_training_matrix(args.datasets, args.limit_per_dataset)

    model = IsolationForest(
        n_estimators=args.n_estimators,
        contamination=args.contamination,
        random_state=args.random_state,
    )
    model.fit(x)

    decisions = model.decision_function(x)
    decision_min = float(np.min(decisions))
    decision_max = float(np.max(decisions))

    model_out = Path(args.model_out)
    model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_out)

    report = {
        "datasets": summaries,
        "rows_total": int(len(x)),
        "feature_order": ["strain", "vibration", "temperature", "humidity"],
        "n_estimators": args.n_estimators,
        "contamination": args.contamination,
        "random_state": args.random_state,
        "decision_min": decision_min,
        "decision_max": decision_max,
        "model_out": str(model_out),
    }

    meta_out = Path(args.meta_out)
    meta_out.parent.mkdir(parents=True, exist_ok=True)
    meta_out.write_text(json.dumps(report, indent=2))
    report["meta_out"] = str(meta_out)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
