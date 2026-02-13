#!/usr/bin/env python3
"""Dataset adapters to map local CSV files into InfraGuard canonical AI records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class CanonicalRecord:
    """Canonical sensor record used by AI pipeline components."""

    strain_value: float
    vibration_rms: float
    temperature: float
    humidity: float
    traffic_density: float | None
    rainfall_intensity: float | None
    timestamp: str


@dataclass
class DatasetSummary:
    """Summary of converted dataset."""

    dataset_path: str
    dataset_kind: str
    rows_loaded: int
    started_at: str | None
    ended_at: str | None


def _to_float(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    stripped = str(value).strip()
    if stripped == "":
        return default
    try:
        return float(stripped)
    except ValueError:
        return default


def _to_iso8601(value: str) -> str:
    raw = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def detect_dataset_kind(path: str | Path) -> str:
    """Detect dataset kind from header columns."""

    with Path(path).open("r", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)

    normalized = [col.strip().lower() for col in header]

    if "strain_microstrain" in normalized and "vibration_ms2" in normalized:
        return "digital_twin"
    if "acceleration_x" in normalized and "fft_magnitude" in normalized:
        return "bridge"
    if any(col.startswith("bearing") for col in normalized):
        return "bearing"

    raise ValueError(f"Unable to detect dataset kind for {path}")


def load_bridge_dataset(path: str | Path, limit: int | None = None) -> list[CanonicalRecord]:
    """Map `bridge_dataset.csv` into canonical records."""

    rows: list[CanonicalRecord] = []
    with Path(path).open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, item in enumerate(reader):
            if limit is not None and idx >= limit:
                break

            ax = _to_float(item.get("acceleration_x"), 0.0) or 0.0
            ay = _to_float(item.get("acceleration_y"), 0.0) or 0.0
            az = _to_float(item.get("acceleration_z"), 0.0) or 0.0

            # Approximation for now: use vector acceleration magnitude as vibration proxy.
            vibration_rms = (ax * ax + ay * ay + az * az) ** 0.5

            fft_mag = _to_float(item.get("fft_magnitude"), 0.0) or 0.0
            # Approximation for now: convert FFT magnitude to pseudo microstrain scale.
            strain_value = _clamp((fft_mag * 700.0), 0.0, 2500.0)

            rows.append(
                CanonicalRecord(
                    strain_value=strain_value,
                    vibration_rms=vibration_rms,
                    temperature=_to_float(item.get("temperature_c"), 25.0) or 25.0,
                    humidity=_clamp(_to_float(item.get("humidity_percent"), 55.0) or 55.0, 0.0, 100.0),
                    traffic_density=None,
                    rainfall_intensity=None,
                    timestamp=_to_iso8601(item.get("timestamp", "")),
                )
            )

    return rows


def load_digital_twin_dataset(path: str | Path, limit: int | None = None) -> list[CanonicalRecord]:
    """Map `bridge_digital_twin_dataset.csv` into canonical records."""

    rows: list[CanonicalRecord] = []
    with Path(path).open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, item in enumerate(reader):
            if limit is not None and idx >= limit:
                break

            traffic_vph = _to_float(item.get("Traffic_Volume_vph"), None)
            traffic_density = None
            if traffic_vph is not None:
                traffic_density = _clamp(traffic_vph / 2000.0, 0.0, 1.0)

            rows.append(
                CanonicalRecord(
                    strain_value=_to_float(item.get("Strain_microstrain"), 0.0) or 0.0,
                    vibration_rms=_to_float(item.get("Vibration_ms2"), 0.0) or 0.0,
                    temperature=_to_float(item.get("Temperature_C"), 25.0) or 25.0,
                    humidity=_clamp(_to_float(item.get("Humidity_percent"), 55.0) or 55.0, 0.0, 100.0),
                    traffic_density=traffic_density,
                    rainfall_intensity=_to_float(item.get("Precipitation_mmh"), None),
                    timestamp=_to_iso8601(item.get("Timestamp", "")),
                )
            )

    return rows


def load_bearing_dataset(path: str | Path, limit: int | None = None) -> list[CanonicalRecord]:
    """Map `merged_dataset_BearingTest_2.csv` into canonical records."""

    rows: list[CanonicalRecord] = []
    with Path(path).open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, item in enumerate(reader):
            if limit is not None and idx >= limit:
                break

            bearing_values = [
                _to_float(item.get("Bearing 1"), 0.0) or 0.0,
                _to_float(item.get("Bearing 2"), 0.0) or 0.0,
                _to_float(item.get("Bearing 3"), 0.0) or 0.0,
                _to_float(item.get("Bearing 4"), 0.0) or 0.0,
            ]
            vibration_rms = sum(abs(v) for v in bearing_values) / float(len(bearing_values))
            strain_value = _clamp(vibration_rms * 1500.0, 0.0, 2500.0)

            timestamp_value = item.get("", "")
            rows.append(
                CanonicalRecord(
                    strain_value=strain_value,
                    vibration_rms=vibration_rms,
                    temperature=25.0,
                    humidity=55.0,
                    traffic_density=None,
                    rainfall_intensity=None,
                    timestamp=_to_iso8601(timestamp_value),
                )
            )

    return rows


def load_canonical_records(
    dataset_path: str | Path,
    dataset_kind: str = "auto",
    limit: int | None = None,
) -> tuple[list[CanonicalRecord], DatasetSummary]:
    """Load dataset and convert to canonical records."""

    path = Path(dataset_path)
    kind = detect_dataset_kind(path) if dataset_kind == "auto" else dataset_kind

    loaders = {
        "bridge": load_bridge_dataset,
        "digital_twin": load_digital_twin_dataset,
        "bearing": load_bearing_dataset,
    }

    if kind not in loaders:
        raise ValueError(f"Unsupported dataset kind: {kind}")

    records = loaders[kind](path, limit=limit)

    summary = DatasetSummary(
        dataset_path=str(path),
        dataset_kind=kind,
        rows_loaded=len(records),
        started_at=records[0].timestamp if records else None,
        ended_at=records[-1].timestamp if records else None,
    )

    return records, summary


def records_to_dicts(records: Iterable[CanonicalRecord]) -> list[dict]:
    """Convert dataclass records to plain dictionaries."""

    return [asdict(record) for record in records]
