#!/usr/bin/env python3
"""Train PyTorch LSTM model for 72-hour failure probability forecasting."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import timedelta
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


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


class SequenceDataset(Dataset):
    """Windowed sequence dataset for LSTM regression."""

    def __init__(self, xs: np.ndarray, ys: np.ndarray):
        self.xs = torch.tensor(xs, dtype=torch.float32)
        self.ys = torch.tensor(ys, dtype=torch.float32).view(-1, 1)

    def __len__(self) -> int:
        return len(self.xs)

    def __getitem__(self, idx: int):
        return self.xs[idx], self.ys[idx]


class LSTMForecaster(nn.Module):
    """Architecture aligned with AI_INTEGRATION.md."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LSTM model using PyTorch")
    parser.add_argument(
        "--dataset",
        default="data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
        help="Path to source CSV",
    )
    parser.add_argument("--seq-len", type=int, default=288, help="Sequence length (10-min samples for 48h)")
    parser.add_argument("--horizon-steps", type=int, default=432, help="Forecast horizon in sequence steps (72h)")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model-out",
        default="data-platform/ml/models/lstm_failure_predictor.pt",
    )
    parser.add_argument(
        "--meta-out",
        default="data-platform/ml/models/lstm_failure_predictor.meta.json",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_dataframe(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], errors="coerce")

    needed = [TIME_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN]
    df = df[needed].copy()

    for col in FEATURE_COLUMNS + [TARGET_COLUMN]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(TIME_COLUMN).set_index(TIME_COLUMN)

    # Resample to 10-minute cadence to keep 48h window tractable.
    df = df.resample("10min").mean()
    df[FEATURE_COLUMNS + [TARGET_COLUMN]] = df[FEATURE_COLUMNS + [TARGET_COLUMN]].interpolate(limit_direction="both")
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])

    return df.reset_index()


def split_indices(n: int) -> tuple[slice, slice, slice]:
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)


def compute_stats(train_df: pd.DataFrame) -> NormalizationStats:
    mins = {col: float(train_df[col].min()) for col in FEATURE_COLUMNS}
    maxs = {col: float(train_df[col].max()) for col in FEATURE_COLUMNS}
    return NormalizationStats(feature_min=mins, feature_max=maxs)


def normalize_features(df: pd.DataFrame, stats: NormalizationStats) -> np.ndarray:
    arr = []
    for col in FEATURE_COLUMNS:
        lower = stats.feature_min[col]
        upper = stats.feature_max[col]
        denom = max(upper - lower, 1e-9)
        values = ((df[col].to_numpy(dtype=np.float32) - lower) / denom).clip(0.0, 1.0)
        arr.append(values)
    return np.stack(arr, axis=1)


def build_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    seq_len: int,
    horizon_steps: int,
) -> tuple[np.ndarray, np.ndarray]:
    xs = []
    ys = []

    last_start = len(features) - seq_len - horizon_steps + 1
    for start in range(max(0, last_start)):
        end = start + seq_len
        target_idx = end + horizon_steps - 1
        xs.append(features[start:end])
        ys.append(np.clip(targets[target_idx], 0.0, 1.0))

    if not xs:
        raise ValueError("Not enough data to build training sequences")

    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def iter_batches(dataset: SequenceDataset, batch_size: int, shuffle: bool) -> DataLoader:
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False)


def evaluate(model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: torch.device) -> float:
    model.eval()
    losses = []
    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            losses.append(float(loss.item()))

    return float(np.mean(losses)) if losses else 0.0


def train(args: argparse.Namespace) -> dict:
    set_seed(args.seed)

    df = load_dataframe(args.dataset)
    n_total = len(df)
    raw_train_slice, raw_val_slice, raw_test_slice = split_indices(n_total)
    train_df = df.iloc[raw_train_slice]
    stats = compute_stats(train_df)

    all_feat = normalize_features(df, stats)
    all_target = df[TARGET_COLUMN].to_numpy(dtype=np.float32)
    x_all, y_all = build_sequences(all_feat, all_target, args.seq_len, args.horizon_steps)

    seq_train_slice, seq_val_slice, seq_test_slice = split_indices(len(x_all))

    x_train, y_train = x_all[seq_train_slice], y_all[seq_train_slice]
    x_val, y_val = x_all[seq_val_slice], y_all[seq_val_slice]
    x_test, y_test = x_all[seq_test_slice], y_all[seq_test_slice]

    train_loader = iter_batches(SequenceDataset(x_train, y_train), args.batch_size, shuffle=True)
    val_loader = iter_batches(SequenceDataset(x_val, y_val), args.batch_size, shuffle=False)
    test_loader = iter_batches(SequenceDataset(x_test, y_test), args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMForecaster(input_size=len(FEATURE_COLUMNS)).to(device)
    loss_fn = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    history = []
    best_val = float("inf")
    best_state = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        batch_losses = []
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)

            optimizer.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optimizer.step()

            batch_losses.append(float(loss.item()))

        train_loss = float(np.mean(batch_losses)) if batch_losses else 0.0
        val_loss = evaluate(model, val_loader, loss_fn, device)

        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

        if val_loss < best_val:
            best_val = val_loss
            best_state = model.state_dict()

    if best_state is not None:
        model.load_state_dict(best_state)

    test_loss = evaluate(model, test_loader, loss_fn, device)

    model_out = Path(args.model_out)
    model_out.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_size": len(FEATURE_COLUMNS),
            "sequence_length": args.seq_len,
            "horizon_steps": args.horizon_steps,
            "feature_columns": FEATURE_COLUMNS,
            "normalization": {
                "feature_min": stats.feature_min,
                "feature_max": stats.feature_max,
            },
            "architecture": [
                "Input(time_steps, features=4)",
                "LSTM(64, return_sequences=True)",
                "Dropout(0.2)",
                "LSTM(32)",
                "Dense(16, relu)",
                "Dense(1, sigmoid)",
            ],
        },
        model_out,
    )

    report = {
        "dataset": str(Path(args.dataset)),
        "rows_total": n_total,
        "train_rows": int(len(df.iloc[raw_train_slice])),
        "val_rows": int(len(df.iloc[raw_val_slice])),
        "test_rows": int(len(df.iloc[raw_test_slice])),
        "sequence_length": args.seq_len,
        "horizon_steps": args.horizon_steps,
        "num_train_sequences": int(len(x_train)),
        "num_val_sequences": int(len(x_val)),
        "num_test_sequences": int(len(x_test)),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "best_val_loss": best_val,
        "test_loss": test_loss,
        "history": history,
        "model_out": str(model_out),
    }

    meta_out = Path(args.meta_out)
    meta_out.parent.mkdir(parents=True, exist_ok=True)
    meta_out.write_text(json.dumps(report, indent=2))
    report["meta_out"] = str(meta_out)

    return report


def main() -> None:
    args = parse_args()
    report = train(args)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
