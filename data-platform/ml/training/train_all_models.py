#!/usr/bin/env python3
"""Train all trainable InfraGuard ML models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train all InfraGuard models")
    parser.add_argument(
        "--digital-twin-dataset",
        default="data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
    )
    parser.add_argument(
        "--bridge-dataset",
        default="data-platform/ml/datasets/bridge_dataset.csv",
    )
    parser.add_argument(
        "--bearing-dataset",
        default="data-platform/ml/datasets/merged_dataset_BearingTest_2.csv",
    )
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=128)
    return parser.parse_args()


def run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def main() -> None:
    args = parse_args()

    lstm_report = run(
        [
            sys.executable,
            "data-platform/ml/training/train_lstm_torch.py",
            "--dataset",
            args.digital_twin_dataset,
            "--epochs",
            str(args.epochs),
            "--batch-size",
            str(args.batch_size),
            "--model-out",
            "data-platform/ml/models/lstm_failure_predictor.pt",
            "--meta-out",
            "data-platform/ml/models/lstm_failure_predictor.meta.json",
        ]
    )

    iso_report = run(
        [
            sys.executable,
            "data-platform/ml/training/train_isolation_forest.py",
            "--datasets",
            args.bridge_dataset,
            args.digital_twin_dataset,
            args.bearing_dataset,
            "--model-out",
            "data-platform/ml/models/isolation_forest.joblib",
            "--meta-out",
            "data-platform/ml/models/isolation_forest.meta.json",
        ]
    )

    summary = {
        "lstm": {
            "model": lstm_report["model_out"],
            "meta": lstm_report["meta_out"],
            "best_val_loss": lstm_report["best_val_loss"],
            "test_loss": lstm_report["test_loss"],
        },
        "isolation_forest": {
            "model": iso_report["model_out"],
            "meta": iso_report["meta_out"],
            "rows_total": iso_report["rows_total"],
        },
    }

    out = Path("data-platform/ml/models/training_summary.json")
    out.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
