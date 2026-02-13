#!/usr/bin/env python3
"""Run Step-2 evaluation for all trained InfraGuard ML models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import resolve_path, utc_now_iso, write_json
from evaluate_isolation_forest import parse_args as parse_iso_args, run as run_iso
from evaluate_lstm_torch import parse_args as parse_lstm_args, run as run_lstm


ROOT = Path(__file__).resolve().parents[3]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate all trained InfraGuard models")
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
    parser.add_argument(
        "--lstm-model-path",
        default="data-platform/ml/models/lstm_failure_predictor.pt",
    )
    parser.add_argument(
        "--isolation-model-path",
        default="data-platform/ml/models/isolation_forest.joblib",
    )
    parser.add_argument(
        "--isolation-meta-path",
        default="data-platform/ml/models/isolation_forest.meta.json",
    )
    parser.add_argument("--risk-threshold", type=float, default=0.6)
    parser.add_argument("--anomaly-threshold", type=float, default=0.65)
    parser.add_argument(
        "--lstm-calibration-split",
        default="all",
        choices=["train", "val", "test", "all"],
    )
    parser.add_argument(
        "--lstm-split-strategy",
        default="event_aware",
        choices=["event_aware", "chronological"],
    )
    parser.add_argument("--lstm-min-proxy-events-val", type=int, default=1)
    parser.add_argument("--lstm-min-proxy-events-test", type=int, default=1)
    parser.add_argument(
        "--out-dir",
        default="data-platform/ml/reports",
    )
    parser.add_argument(
        "--summary-out",
        default="data-platform/ml/reports/evaluation_summary.json",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict:
    out_dir = resolve_path(ROOT, args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_out = resolve_path(ROOT, args.summary_out)

    lstm_args = parse_lstm_args(
        [
            "--dataset",
            args.digital_twin_dataset,
            "--model-path",
            args.lstm_model_path,
            "--risk-threshold",
            str(args.risk_threshold),
            "--calibration-split",
            args.lstm_calibration_split,
            "--split-strategy",
            args.lstm_split_strategy,
            "--min-proxy-events-val",
            str(args.lstm_min_proxy_events_val),
            "--min-proxy-events-test",
            str(args.lstm_min_proxy_events_test),
            "--report-out",
            str(out_dir / "lstm_backtest_report.json"),
            "--predictions-out",
            str(out_dir / "lstm_backtest_predictions.csv"),
            "--split",
            "test",
        ]
    )
    lstm_report = run_lstm(lstm_args)

    iso_args = parse_iso_args(
        [
            "--datasets",
            args.bridge_dataset,
            args.digital_twin_dataset,
            args.bearing_dataset,
            "--model-path",
            args.isolation_model_path,
            "--meta-path",
            args.isolation_meta_path,
            "--anomaly-threshold",
            str(args.anomaly_threshold),
            "--report-out",
            str(out_dir / "isolation_forest_evaluation_report.json"),
        ]
    )
    iso_report = run_iso(iso_args)

    summary = {
        "generated_at": utc_now_iso(),
        "lstm": {
            "report_out": lstm_report["report_out"],
            "split_strategy_applied": (lstm_report.get("split_strategy", {}) or {}).get("strategy_applied"),
            "split_strategy_fallback_reason": (lstm_report.get("split_strategy", {}) or {}).get("fallback_reason"),
            "test_rmse": lstm_report["metrics"]["regression"]["rmse"],
            "test_mae": lstm_report["metrics"]["regression"]["mae"],
            "test_r2": lstm_report["metrics"]["regression"]["r2"],
            "test_high_risk_f1": lstm_report["metrics"]["thresholded_classification"]["f1"],
            "proxy_event_f1_at_recommended_threshold": (
                lstm_report.get("proxy_event_metrics_at_recommended_threshold", {}) or {}
            ).get("f1"),
            "proxy_event_positive_rate_eval_split": (
                lstm_report.get("proxy_event_context", {}) or {}
            ).get("evaluated_positive_rate"),
            "proxy_event_positive_rate_calibration_split": (
                lstm_report.get("proxy_event_calibration_context", {}) or {}
            ).get("positive_rate"),
            "proxy_event_recommended_threshold": (
                lstm_report.get("proxy_event_recommended_threshold", {}) or {}
            ).get("threshold"),
            "proxy_event_recommended_f1": (
                lstm_report.get("proxy_event_recommended_threshold", {}) or {}
            ).get("f1"),
        },
        "isolation_forest": {
            "report_out": iso_report["report_out"],
            "rows_scored_total": iso_report["rows_scored_total"],
            "flagged_rate_total": iso_report["flagged_rate_total"],
            "proxy_f1_total": iso_report.get("proxy_classification_metrics_total", {}).get("f1"),
            "proxy_recommended_threshold_total": (
                iso_report.get("proxy_recommended_threshold_total", {}) or {}
            ).get("threshold"),
            "proxy_recommended_f1_total": (
                iso_report.get("proxy_recommended_threshold_total", {}) or {}
            ).get("f1"),
        },
    }

    write_json(summary_out, summary)
    summary["summary_out"] = str(summary_out)
    return summary


def main() -> None:
    args = parse_args()
    summary = run(args)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
