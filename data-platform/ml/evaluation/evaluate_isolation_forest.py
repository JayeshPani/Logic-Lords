#!/usr/bin/env python3
"""Evaluate trained Isolation Forest model across InfraGuard datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

from common import (
    binary_metrics,
    load_json,
    resolve_path,
    score_distribution,
    sweep_binary_thresholds,
    utc_now_iso,
    write_json,
)


ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT / "scripts"))
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))

from dataset_adapters import load_canonical_records, records_to_dicts  # noqa: E402
from lstm_forecast.config import Settings as ForecastSettings  # noqa: E402
from lstm_forecast.preprocessing import SensorNormalizer  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate trained Isolation Forest model")
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
    parser.add_argument(
        "--model-path",
        default="data-platform/ml/models/isolation_forest.joblib",
    )
    parser.add_argument(
        "--meta-path",
        default="data-platform/ml/models/isolation_forest.meta.json",
    )
    parser.add_argument(
        "--report-out",
        default="data-platform/ml/reports/isolation_forest_evaluation_report.json",
    )
    parser.add_argument("--scores-out", default=None)
    parser.add_argument("--anomaly-threshold", type=float, default=0.65)
    parser.add_argument("--threshold-sweep-start", type=float, default=0.40)
    parser.add_argument("--threshold-sweep-end", type=float, default=0.95)
    parser.add_argument("--threshold-sweep-step", type=float, default=0.05)
    parser.add_argument(
        "--digital-twin-proxy-threshold",
        type=float,
        default=0.7,
        help="Threshold for Anomaly_Detection_Score when creating proxy labels",
    )
    parser.add_argument(
        "--bridge-condition-threshold",
        type=int,
        default=2,
        help="Rows with structural_condition >= this threshold are treated as proxy positives",
    )
    parser.add_argument("--top-n", type=int, default=25)
    return parser.parse_args(argv)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + float(np.exp(-value)))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_decision_score(decision: float, minimum: float | None, maximum: float | None) -> float:
    if minimum is None or maximum is None or (maximum - minimum) <= 1e-9:
        return _clamp01(_sigmoid(-5.0 * decision))

    normalized_inverse = (maximum - decision) / (maximum - minimum)
    return _clamp01(float(normalized_inverse))


def _threshold_grid(start: float, end: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("threshold-sweep-step must be > 0")
    if end < start:
        raise ValueError("threshold-sweep-end must be >= threshold-sweep-start")
    grid = np.arange(start, end + 1e-12, step)
    return [float(max(0.0, min(1.0, value))) for value in grid]


def _load_proxy_labels(
    dataset_path: Path,
    kind: str,
    limit: int | None,
    digital_twin_threshold: float,
    bridge_condition_threshold: int,
) -> tuple[list[int] | None, dict]:
    nrows = limit if limit is not None else None
    frame = pd.read_csv(dataset_path, nrows=nrows)

    if kind == "digital_twin":
        numeric = lambda col: pd.to_numeric(frame.get(col, 0), errors="coerce").fillna(0.0)
        labels = (
            (numeric("Maintenance_Alert") > 0.0)
            | (numeric("Flood_Event_Flag") > 0.0)
            | (numeric("High_Winds_Storms") > 0.0)
            | (numeric("Abnormal_Traffic_Load_Surges") > 0.0)
            | (numeric("Anomaly_Detection_Score") >= digital_twin_threshold)
        )
        return labels.astype(np.int32).tolist(), {
            "label_mode": "proxy",
            "proxy_rule": "Maintenance_Alert OR Flood_Event_Flag OR High_Winds_Storms OR Abnormal_Traffic_Load_Surges OR Anomaly_Detection_Score>=threshold",
            "digital_twin_proxy_threshold": digital_twin_threshold,
        }

    if kind == "bridge":
        condition = pd.to_numeric(frame.get("structural_condition", 0), errors="coerce").fillna(0.0)
        labels = (condition >= float(bridge_condition_threshold)).astype(np.int32).tolist()
        return labels, {
            "label_mode": "proxy",
            "proxy_rule": "structural_condition>=threshold",
            "bridge_condition_threshold": bridge_condition_threshold,
        }

    return None, {
        "label_mode": "none",
        "proxy_rule": "no labels available for this dataset kind",
    }


def run(args: argparse.Namespace) -> dict:
    model_path = resolve_path(ROOT, args.model_path)
    meta_path = resolve_path(ROOT, args.meta_path)
    report_out = resolve_path(ROOT, args.report_out)
    scores_out = resolve_path(ROOT, args.scores_out) if args.scores_out else None

    model = joblib.load(model_path)
    meta = load_json(meta_path)
    decision_min = float(meta["decision_min"]) if "decision_min" in meta else None
    decision_max = float(meta["decision_max"]) if "decision_max" in meta else None

    normalizer = SensorNormalizer(ForecastSettings())

    rows: list[dict] = []
    dataset_reports: list[dict] = []
    labeled_true: list[int] = []
    labeled_pred: list[int] = []
    labeled_scores: list[float] = []

    for dataset_arg in args.datasets:
        dataset_path = resolve_path(ROOT, dataset_arg)
        records, summary = load_canonical_records(dataset_path, dataset_kind="auto", limit=args.limit_per_dataset)
        records_dict = records_to_dicts(records)
        labels, label_meta = _load_proxy_labels(
            dataset_path=dataset_path,
            kind=summary.dataset_kind,
            limit=args.limit_per_dataset,
            digital_twin_threshold=args.digital_twin_proxy_threshold,
            bridge_condition_threshold=args.bridge_condition_threshold,
        )

        usable = len(records_dict)
        if labels is not None:
            usable = min(usable, len(labels))

        dataset_scores: list[float] = []
        dataset_flags: list[int] = []
        dataset_true: list[int] = []
        dataset_pred: list[int] = []

        for idx in range(usable):
            raw = records_dict[idx]
            normalized = normalizer.normalize_record(raw)
            features = [
                normalized["strain"],
                normalized["vibration"],
                normalized["temperature"],
                normalized["humidity"],
            ]
            decision = float(model.decision_function([features])[0])
            score = _normalize_decision_score(decision, decision_min, decision_max)
            flag = int(score >= args.anomaly_threshold)

            label = labels[idx] if labels is not None else None
            if label is not None:
                dataset_true.append(int(label))
                dataset_pred.append(flag)
                labeled_true.append(int(label))
                labeled_pred.append(flag)
                labeled_scores.append(score)

            dataset_scores.append(score)
            dataset_flags.append(flag)
            rows.append(
                {
                    "dataset": summary.dataset_path,
                    "dataset_kind": summary.dataset_kind,
                    "timestamp": raw.get("timestamp"),
                    "anomaly_score": score,
                    "anomaly_flag": flag,
                    "proxy_label": label,
                    "strain": features[0],
                    "vibration": features[1],
                    "temperature": features[2],
                    "humidity": features[3],
                }
            )

        if not dataset_scores:
            continue

        report = {
            "dataset": summary.dataset_path,
            "dataset_kind": summary.dataset_kind,
            "rows_scored": int(len(dataset_scores)),
            "flagged_count": int(np.sum(dataset_flags)),
            "flagged_rate": float(np.mean(dataset_flags)),
            "score_distribution": score_distribution(np.asarray(dataset_scores, dtype=np.float32)),
            "labels": label_meta,
        }
        if dataset_true:
            report["proxy_classification_metrics"] = binary_metrics(
                np.asarray(dataset_true, dtype=np.int32),
                np.asarray(dataset_pred, dtype=np.int32),
            )
            report["proxy_positive_rate"] = float(np.mean(dataset_true))

        dataset_reports.append(report)

    if not rows:
        raise RuntimeError("No rows were scored during Isolation Forest evaluation")

    all_scores = np.asarray([row["anomaly_score"] for row in rows], dtype=np.float32)
    all_flags = np.asarray([row["anomaly_flag"] for row in rows], dtype=np.int32)

    ranked = sorted(rows, key=lambda item: item["anomaly_score"], reverse=True)
    top_anomalies = ranked[: args.top_n]

    report = {
        "generated_at": utc_now_iso(),
        "model_path": str(model_path),
        "meta_path": str(meta_path),
        "anomaly_threshold": float(args.anomaly_threshold),
        "decision_calibration": {
            "decision_min": decision_min,
            "decision_max": decision_max,
        },
        "rows_scored_total": int(len(rows)),
        "flagged_total": int(np.sum(all_flags)),
        "flagged_rate_total": float(np.mean(all_flags)),
        "score_distribution_total": score_distribution(all_scores),
        "dataset_reports": dataset_reports,
        "top_anomalies": top_anomalies,
    }

    if labeled_true:
        report["proxy_classification_metrics_total"] = binary_metrics(
            np.asarray(labeled_true, dtype=np.int32),
            np.asarray(labeled_pred, dtype=np.int32),
        )
        report["proxy_positive_rate_total"] = float(np.mean(labeled_true))
        sweep_rows, sweep_best = sweep_binary_thresholds(
            np.asarray(labeled_scores, dtype=np.float32),
            np.asarray(labeled_true, dtype=np.int32),
            _threshold_grid(args.threshold_sweep_start, args.threshold_sweep_end, args.threshold_sweep_step),
        )
        report["proxy_threshold_sweep_total"] = sweep_rows
        report["proxy_recommended_threshold_total"] = sweep_best

    if scores_out is not None:
        scores_out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(scores_out, index=False)
        report["scores_out"] = str(scores_out)

    write_json(report_out, report)
    report["report_out"] = str(report_out)
    return report


def main() -> None:
    args = parse_args()
    report = run(args)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
