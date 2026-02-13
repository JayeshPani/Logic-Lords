#!/usr/bin/env python3
"""Shared utilities for model evaluation and backtesting scripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "Strain_microstrain",
    "Vibration_ms2",
    "Temperature_C",
    "Humidity_percent",
]
TARGET_COLUMN = "Probability_of_Failure_PoF"
TIME_COLUMN = "Timestamp"


@dataclass(frozen=True)
class NormalizationStats:
    feature_min: dict[str, float]
    feature_max: dict[str, float]


def resolve_path(root: Path, value: str) -> Path:
    """Resolve path from cwd first, then repository root."""

    candidate = Path(value)
    if candidate.exists():
        return candidate
    if candidate.is_absolute():
        return candidate
    rooted = root / candidate
    return rooted


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def load_forecast_dataframe(path: str) -> pd.DataFrame:
    """Load forecast dataset with training-compatible preprocessing."""

    df = pd.read_csv(path)
    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], errors="coerce")
    needed = [TIME_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN]
    df = df[needed].copy()

    for col in FEATURE_COLUMNS + [TARGET_COLUMN]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(TIME_COLUMN).set_index(TIME_COLUMN)
    df = df.resample("10min").mean()
    df[FEATURE_COLUMNS + [TARGET_COLUMN]] = df[FEATURE_COLUMNS + [TARGET_COLUMN]].interpolate(limit_direction="both")
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])

    return df.reset_index()


def normalize_features(df: pd.DataFrame, stats: NormalizationStats) -> np.ndarray:
    values = []
    for col in FEATURE_COLUMNS:
        lower = float(stats.feature_min[col])
        upper = float(stats.feature_max[col])
        denom = max(upper - lower, 1e-9)
        normalized = ((df[col].to_numpy(dtype=np.float32) - lower) / denom).clip(0.0, 1.0)
        values.append(normalized)
    return np.stack(values, axis=1)


def build_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    seq_len: int,
    horizon_steps: int,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    xs = []
    ys = []
    target_indices: list[int] = []

    last_start = len(features) - seq_len - horizon_steps + 1
    for start in range(max(0, last_start)):
        end = start + seq_len
        target_idx = end + horizon_steps - 1
        xs.append(features[start:end])
        ys.append(np.clip(targets[target_idx], 0.0, 1.0))
        target_indices.append(target_idx)

    if not xs:
        raise ValueError("Not enough rows to build evaluation sequences")

    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32), target_indices


def split_indices(n: int) -> tuple[slice, slice, slice]:
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    diff = y_pred - y_true
    mse = float(np.mean(np.square(diff)))
    rmse = float(np.sqrt(mse))
    mae = float(np.mean(np.abs(diff)))

    denom = np.maximum(np.abs(y_true), 1e-6)
    mape = float(np.mean(np.abs(diff) / denom) * 100.0)

    ss_res = float(np.sum(np.square(diff)))
    y_mean = float(np.mean(y_true))
    ss_tot = float(np.sum(np.square(y_true - y_mean)))
    r2 = 0.0 if ss_tot <= 1e-12 else float(1.0 - (ss_res / ss_tot))

    return {
        "mse": mse,
        "rmse": rmse,
        "mae": mae,
        "mape_pct": mape,
        "r2": r2,
    }


def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int]:
    y_true_i = y_true.astype(np.int32)
    y_pred_i = y_pred.astype(np.int32)

    tp = int(np.sum((y_true_i == 1) & (y_pred_i == 1)))
    tn = int(np.sum((y_true_i == 0) & (y_pred_i == 0)))
    fp = int(np.sum((y_true_i == 0) & (y_pred_i == 1)))
    fn = int(np.sum((y_true_i == 1) & (y_pred_i == 0)))

    total = max(1, len(y_true_i))
    accuracy = float((tp + tn) / total)
    precision = float(tp / max(1, tp + fp))
    recall = float(tp / max(1, tp + fn))
    f1 = float((2.0 * precision * recall) / max(1e-12, precision + recall))

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "support": int(len(y_true_i)),
    }


def sweep_binary_thresholds(
    scores: np.ndarray,
    labels: np.ndarray,
    thresholds: list[float],
) -> tuple[list[dict], dict | None]:
    """Compute classification metrics across thresholds and pick best F1."""

    rows: list[dict] = []
    best: dict | None = None

    for threshold in thresholds:
        preds = (scores >= float(threshold)).astype(np.int32)
        metrics = binary_metrics(labels.astype(np.int32), preds)
        row = {
            "threshold": float(threshold),
            **metrics,
            "predicted_positive_rate": float(np.mean(preds)) if len(preds) else 0.0,
        }
        rows.append(row)

        if best is None:
            best = row
            continue

        # Primary objective: highest F1. Tie-breakers: higher accuracy, recall, then precision.
        if (
            row["f1"] > best["f1"]
            or (
                row["f1"] == best["f1"]
                and (
                    row["accuracy"] > best["accuracy"]
                    or (
                        row["accuracy"] == best["accuracy"]
                        and (
                            row["recall"] > best["recall"]
                            or (
                                row["recall"] == best["recall"]
                                and row["precision"] > best["precision"]
                            )
                        )
                    )
                )
            )
        ):
            best = row

    return rows, best


def calibration_bins(y_true: np.ndarray, y_pred: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict] = []
    for i in range(bins):
        lower = float(edges[i])
        upper = float(edges[i + 1])
        if i == bins - 1:
            mask = (y_pred >= lower) & (y_pred <= upper)
        else:
            mask = (y_pred >= lower) & (y_pred < upper)

        count = int(np.sum(mask))
        avg_pred = float(np.mean(y_pred[mask])) if count else 0.0
        avg_true = float(np.mean(y_true[mask])) if count else 0.0
        rows.append(
            {
                "bin_start": lower,
                "bin_end": upper,
                "count": count,
                "avg_prediction": avg_pred,
                "avg_actual": avg_true,
            }
        )
    return rows


def score_distribution(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }
