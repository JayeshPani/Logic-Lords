#!/usr/bin/env python3
"""Evaluate trained Torch LSTM model with backtesting metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from common import (
    NormalizationStats,
    TARGET_COLUMN,
    TIME_COLUMN,
    binary_metrics,
    build_sequences,
    calibration_bins,
    load_forecast_dataframe,
    normalize_features,
    regression_metrics,
    resolve_path,
    score_distribution,
    split_indices,
    sweep_binary_thresholds,
    utc_now_iso,
    write_json,
)


ROOT = Path(__file__).resolve().parents[3]


class LSTMForecaster(nn.Module):
    """Architecture aligned with model training script."""

    def __init__(self, input_size: int):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size=input_size, hidden_size=64, batch_first=True)
        self.dropout = nn.Dropout(0.2)
        self.lstm2 = nn.LSTM(input_size=64, hidden_size=32, batch_first=True)
        self.fc1 = nn.Linear(32, 16)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x, _ = self.lstm1(x)
        x = self.dropout(x)
        x, _ = self.lstm2(x)
        x = x[:, -1, :]
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return self.sigmoid(x)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate trained Torch LSTM model")
    parser.add_argument(
        "--dataset",
        default="data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
    )
    parser.add_argument(
        "--model-path",
        default="data-platform/ml/models/lstm_failure_predictor.pt",
    )
    parser.add_argument(
        "--report-out",
        default="data-platform/ml/reports/lstm_backtest_report.json",
    )
    parser.add_argument(
        "--predictions-out",
        default="data-platform/ml/reports/lstm_backtest_predictions.csv",
    )
    parser.add_argument(
        "--split",
        default="test",
        choices=["train", "val", "test", "all"],
        help="Split to evaluate using 70/15/15 chronology split",
    )
    parser.add_argument(
        "--calibration-split",
        default="all",
        choices=["train", "val", "test", "all"],
        help="Split used for proxy-event threshold sweep calibration",
    )
    parser.add_argument("--seq-len", type=int, default=None)
    parser.add_argument("--horizon-steps", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument(
        "--risk-threshold",
        type=float,
        default=0.6,
        help="Threshold to convert PoF values into risk flags for classification-style metrics",
    )
    parser.add_argument("--threshold-sweep-start", type=float, default=0.05)
    parser.add_argument("--threshold-sweep-end", type=float, default=0.95)
    parser.add_argument("--threshold-sweep-step", type=float, default=0.05)
    parser.add_argument(
        "--split-strategy",
        default="event_aware",
        choices=["event_aware", "chronological"],
        help="How train/val/test slices are selected before reporting",
    )
    parser.add_argument("--min-train-ratio", type=float, default=0.50)
    parser.add_argument("--min-val-ratio", type=float, default=0.05)
    parser.add_argument("--min-test-ratio", type=float, default=0.05)
    parser.add_argument("--min-proxy-events-val", type=int, default=1)
    parser.add_argument("--min-proxy-events-test", type=int, default=1)
    return parser.parse_args(argv)


def _infer(
    model: nn.Module,
    x_eval: np.ndarray,
    batch_size: int,
) -> np.ndarray:
    model.eval()
    predictions = []
    with torch.no_grad():
        for offset in range(0, len(x_eval), batch_size):
            chunk = torch.tensor(x_eval[offset : offset + batch_size], dtype=torch.float32)
            pred = model(chunk).cpu().numpy().reshape(-1)
            predictions.append(pred)
    if not predictions:
        return np.asarray([], dtype=np.float32)
    return np.clip(np.concatenate(predictions), 0.0, 1.0)


def _load_proxy_event_labels(dataset_path: Path, timeline: pd.Series) -> tuple[np.ndarray | None, dict]:
    """Load event-style proxy labels aligned to resampled timeline."""

    event_columns = [
        "Maintenance_Alert",
        "Flood_Event_Flag",
        "High_Winds_Storms",
        "Abnormal_Traffic_Load_Surges",
    ]
    raw = pd.read_csv(dataset_path)
    if TIME_COLUMN not in raw.columns:
        return None, {"label_mode": "none", "reason": "Timestamp column missing"}

    available = [col for col in event_columns if col in raw.columns]
    if not available:
        return None, {"label_mode": "none", "reason": "No proxy event columns present"}

    raw[TIME_COLUMN] = pd.to_datetime(raw[TIME_COLUMN], errors="coerce")
    raw = raw.dropna(subset=[TIME_COLUMN]).set_index(TIME_COLUMN).sort_index()
    for col in available:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0.0)

    events_10m = raw[available].resample("10min").max()
    event_any = (events_10m.max(axis=1) > 0.0).astype(np.int32)
    aligned = event_any.reindex(pd.to_datetime(timeline), fill_value=0).astype(np.int32).to_numpy()

    return aligned, {
        "label_mode": "proxy",
        "proxy_rule": "Maintenance_Alert OR Flood_Event_Flag OR High_Winds_Storms OR Abnormal_Traffic_Load_Surges",
        "columns_used": available,
        "positive_rate_over_rows": float(np.mean(aligned)) if len(aligned) else 0.0,
        "positive_count_over_rows": int(np.sum(aligned)),
    }


def _threshold_grid(start: float, end: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("threshold-sweep-step must be > 0")
    if end < start:
        raise ValueError("threshold-sweep-end must be >= threshold-sweep-start")
    grid = np.arange(start, end + 1e-12, step)
    return [float(max(0.0, min(1.0, value))) for value in grid]


def _make_slice_map(train_end: int, val_end: int, total: int) -> dict[str, slice]:
    return {
        "train": slice(0, train_end),
        "val": slice(train_end, val_end),
        "test": slice(val_end, total),
        "all": slice(0, total),
    }


def _split_stats(labels_seq: np.ndarray, slice_map: dict[str, slice]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key in ("train", "val", "test"):
        part = labels_seq[slice_map[key]]
        out[key] = {
            "size": int(len(part)),
            "proxy_event_count": int(np.sum(part)),
            "proxy_event_rate": float(np.mean(part)) if len(part) else 0.0,
        }
    return out


def _max_train_end_with_events(
    prefix: np.ndarray,
    train_min: int,
    train_max: int,
    val_end: int,
    min_events: int,
) -> int | None:
    """Find the largest train_end that still leaves enough events in val slice."""

    def events_in_val(train_end: int) -> int:
        return int(prefix[val_end] - prefix[train_end])

    if events_in_val(train_min) < min_events:
        return None

    lo = train_min
    hi = train_max
    best = train_min
    while lo <= hi:
        mid = (lo + hi) // 2
        if events_in_val(mid) >= min_events:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _choose_slices(
    total: int,
    labels_seq: np.ndarray | None,
    args: argparse.Namespace,
) -> tuple[dict[str, slice], dict]:
    train_slice, val_slice, test_slice = split_indices(total)
    default_map = {
        "train": train_slice,
        "val": val_slice,
        "test": test_slice,
        "all": slice(0, total),
    }

    if args.split_strategy == "chronological" or labels_seq is None:
        return default_map, {
            "strategy_requested": args.split_strategy,
            "strategy_applied": "chronological",
            "fallback_reason": None if args.split_strategy == "chronological" else "no_proxy_labels",
            "split_stats": _split_stats(labels_seq if labels_seq is not None else np.zeros(total), default_map),
        }

    if total < 3:
        return default_map, {
            "strategy_requested": args.split_strategy,
            "strategy_applied": "chronological",
            "fallback_reason": "too_few_sequences",
            "split_stats": _split_stats(labels_seq, default_map),
        }

    min_train = max(1, int(total * args.min_train_ratio))
    min_val = max(1, int(total * args.min_val_ratio))
    min_test = max(1, int(total * args.min_test_ratio))
    if (min_train + min_val + min_test) >= total:
        return default_map, {
            "strategy_requested": args.split_strategy,
            "strategy_applied": "chronological",
            "fallback_reason": "ratio_constraints_too_strict",
            "split_stats": _split_stats(labels_seq, default_map),
        }

    desired_train_end = int(total * 0.70)
    desired_val_end = int(total * 0.85)
    prefix = np.concatenate([np.array([0], dtype=np.int64), np.cumsum(labels_seq.astype(np.int64))])

    def test_events(val_end: int) -> int:
        return int(prefix[total] - prefix[val_end])

    best: tuple[int, int, int] | None = None  # (cost, train_end, val_end)

    val_end_start = min_train + min_val
    val_end_end = total - min_test
    for val_end in range(val_end_start, val_end_end + 1):
        if test_events(val_end) < args.min_proxy_events_test:
            continue

        train_min = min_train
        train_max = val_end - min_val
        if train_min > train_max:
            continue

        max_train = _max_train_end_with_events(
            prefix=prefix,
            train_min=train_min,
            train_max=train_max,
            val_end=val_end,
            min_events=args.min_proxy_events_val,
        )
        if max_train is None:
            continue

        train_end = min(max_train, max(train_min, desired_train_end))
        cost = abs(train_end - desired_train_end) + abs(val_end - desired_val_end)
        if best is None or cost < best[0]:
            best = (cost, train_end, val_end)

    if best is None:
        return default_map, {
            "strategy_requested": args.split_strategy,
            "strategy_applied": "chronological",
            "fallback_reason": "no_feasible_event_aware_split",
            "split_stats": _split_stats(labels_seq, default_map),
        }

    _, train_end, val_end = best
    slice_map = _make_slice_map(train_end=train_end, val_end=val_end, total=total)
    return slice_map, {
        "strategy_requested": args.split_strategy,
        "strategy_applied": "event_aware",
        "fallback_reason": None,
        "min_train_ratio": args.min_train_ratio,
        "min_val_ratio": args.min_val_ratio,
        "min_test_ratio": args.min_test_ratio,
        "min_proxy_events_val": args.min_proxy_events_val,
        "min_proxy_events_test": args.min_proxy_events_test,
        "boundaries": {
            "train_end": train_end,
            "val_end": val_end,
            "total_sequences": total,
        },
        "split_stats": _split_stats(labels_seq, slice_map),
    }


def run(args: argparse.Namespace) -> dict:
    dataset_path = resolve_path(ROOT, args.dataset)
    model_path = resolve_path(ROOT, args.model_path)
    report_out = resolve_path(ROOT, args.report_out)
    predictions_out = resolve_path(ROOT, args.predictions_out)

    checkpoint = torch.load(model_path, map_location="cpu")
    input_size = int(checkpoint.get("input_size", 4))
    seq_len = int(args.seq_len or checkpoint.get("sequence_length", 288))
    horizon_steps = int(args.horizon_steps or checkpoint.get("horizon_steps", 432))

    normalization = checkpoint.get("normalization", {})
    if "feature_min" not in normalization or "feature_max" not in normalization:
        raise RuntimeError("LSTM checkpoint is missing normalization stats")

    stats = NormalizationStats(
        feature_min={k: float(v) for k, v in normalization["feature_min"].items()},
        feature_max={k: float(v) for k, v in normalization["feature_max"].items()},
    )

    df = load_forecast_dataframe(str(dataset_path))
    features = normalize_features(df, stats)
    targets = df[TARGET_COLUMN].to_numpy(dtype=np.float32)

    x_all, y_all, target_indices = build_sequences(features, targets, seq_len, horizon_steps)
    proxy_labels_all, proxy_meta = _load_proxy_event_labels(dataset_path, df[TIME_COLUMN])
    labels_seq = proxy_labels_all[target_indices].astype(np.int32) if proxy_labels_all is not None else None
    slice_map, split_strategy_meta = _choose_slices(len(x_all), labels_seq, args)

    selected_slice = slice_map[args.split]
    calibration_slice = slice_map[args.calibration_split]
    x_eval = x_all[selected_slice]
    y_eval = y_all[selected_slice]
    eval_target_indices = target_indices[selected_slice]
    x_cal = x_all[calibration_slice]
    if len(x_eval) == 0:
        raise RuntimeError(f"No sequences available for split={args.split}")
    if len(x_cal) == 0:
        raise RuntimeError(f"No sequences available for calibration_split={args.calibration_split}")

    model = LSTMForecaster(input_size=input_size)
    model.load_state_dict(checkpoint["state_dict"])
    preds = _infer(model, x_eval, args.batch_size)
    preds_cal = preds if args.calibration_split == args.split else _infer(model, x_cal, args.batch_size)

    reg = regression_metrics(y_eval, preds)
    y_true_flag = (y_eval >= args.risk_threshold).astype(np.int32)
    y_pred_flag = (preds >= args.risk_threshold).astype(np.int32)
    cls = binary_metrics(y_true_flag, y_pred_flag)
    cal = calibration_bins(y_eval, preds, bins=10)
    thresholds = _threshold_grid(args.threshold_sweep_start, args.threshold_sweep_end, args.threshold_sweep_step)

    timestamps = pd.to_datetime(df.iloc[eval_target_indices][TIME_COLUMN], errors="coerce")
    proxy_event = None
    proxy_event_cal = None
    proxy_event_metrics_at_threshold = None
    proxy_event_metrics_at_recommended = None
    proxy_event_threshold_sweep = None
    proxy_event_recommended_threshold = None
    proxy_event_calibration_context = None
    if labels_seq is not None:
        proxy_event = labels_seq[selected_slice].astype(np.int32)
        proxy_event_cal = labels_seq[calibration_slice].astype(np.int32)
        proxy_event_metrics_at_threshold = binary_metrics(proxy_event, y_pred_flag)
        sweep_rows, sweep_best = sweep_binary_thresholds(preds_cal, proxy_event_cal, thresholds)
        proxy_event_threshold_sweep = sweep_rows
        proxy_event_recommended_threshold = sweep_best
        proxy_event_calibration_context = {
            "split": args.calibration_split,
            "support": int(len(proxy_event_cal)),
            "positive_count": int(np.sum(proxy_event_cal)),
            "positive_rate": float(np.mean(proxy_event_cal)),
        }
        if sweep_best is not None:
            eval_with_recommended = (preds >= float(sweep_best["threshold"])).astype(np.int32)
            proxy_event_metrics_at_recommended = binary_metrics(proxy_event, eval_with_recommended)

    pred_rows = pd.DataFrame(
        {
            "target_timestamp": timestamps.dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "actual_pof": y_eval,
            "predicted_pof": preds,
            "absolute_error": np.abs(y_eval - preds),
            "actual_high_risk_flag": y_true_flag,
            "predicted_high_risk_flag": y_pred_flag,
            "proxy_event_label": proxy_event if proxy_event is not None else np.zeros(len(y_eval), dtype=np.int32),
        }
    )
    predictions_out.parent.mkdir(parents=True, exist_ok=True)
    pred_rows.to_csv(predictions_out, index=False)

    error_order = np.argsort(-np.abs(y_eval - preds))[:10]
    top_errors = [
        {
            "target_timestamp": str(pred_rows.iloc[i]["target_timestamp"]),
            "actual_pof": float(y_eval[i]),
            "predicted_pof": float(preds[i]),
            "absolute_error": float(abs(y_eval[i] - preds[i])),
        }
        for i in error_order
    ]

    report = {
        "generated_at": utc_now_iso(),
        "dataset": str(dataset_path),
        "model_path": str(model_path),
        "split": args.split,
        "calibration_split": args.calibration_split,
        "split_strategy": split_strategy_meta,
        "sequence_length": seq_len,
        "horizon_steps": horizon_steps,
        "risk_threshold": float(args.risk_threshold),
        "rows_after_resample": int(len(df)),
        "num_sequences_total": int(len(x_all)),
        "num_sequences_evaluated": int(len(x_eval)),
        "prediction_distribution": score_distribution(preds),
        "actual_distribution": score_distribution(y_eval),
        "metrics": {
            "regression": reg,
            "thresholded_classification": cls,
        },
        "classification_context": {
            "actual_high_risk_count": int(np.sum(y_true_flag)),
            "predicted_high_risk_count": int(np.sum(y_pred_flag)),
            "actual_high_risk_rate": float(np.mean(y_true_flag)),
            "predicted_high_risk_rate": float(np.mean(y_pred_flag)),
        },
        "proxy_event_labels": proxy_meta,
        "proxy_event_context": {
            "evaluated_positive_count": int(np.sum(proxy_event)) if proxy_event is not None else None,
            "evaluated_positive_rate": float(np.mean(proxy_event)) if proxy_event is not None else None,
        },
        "proxy_event_calibration_context": proxy_event_calibration_context,
        "proxy_event_metrics_at_risk_threshold": proxy_event_metrics_at_threshold,
        "proxy_event_metrics_at_recommended_threshold": proxy_event_metrics_at_recommended,
        "proxy_event_threshold_sweep": proxy_event_threshold_sweep,
        "proxy_event_recommended_threshold": proxy_event_recommended_threshold,
        "calibration_bins": cal,
        "top_absolute_errors": top_errors,
        "predictions_out": str(predictions_out),
    }

    write_json(report_out, report)
    report["report_out"] = str(report_out)
    return report


def main() -> None:
    args = parse_args()
    report = run(args)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
