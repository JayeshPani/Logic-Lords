#!/usr/bin/env python3
"""Verify AI runtime is using trained model configuration."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))
sys.path.append(str(ROOT / "services/anomaly-detection-service/src"))

from lstm_forecast.config import get_settings as get_forecast_settings
from lstm_forecast.predictor import PredictorFactory
from anomaly_detection.config import get_settings as get_anomaly_settings
from anomaly_detection.engine import AnomalyDetector


def _resolve(root: Path, value: str | None) -> str | None:
    if value is None:
        return None
    p = Path(value)
    if p.exists():
        return str(p)
    candidate = root / p
    return str(candidate)


def main() -> None:
    forecast_settings = get_forecast_settings()
    anomaly_settings = get_anomaly_settings()

    predictor = PredictorFactory.create(forecast_settings)
    anomaly_detector = AnomalyDetector(anomaly_settings)

    report = {
        "forecast_predictor_mode": forecast_settings.predictor_mode,
        "forecast_torch_model_path": _resolve(ROOT, forecast_settings.torch_model_path),
        "forecast_predictor_class": predictor.__class__.__name__,
        "anomaly_pretrained_model_path": _resolve(ROOT, anomaly_settings.pretrained_model_path),
        "anomaly_pretrained_meta_path": _resolve(ROOT, anomaly_settings.pretrained_meta_path),
        "anomaly_has_pretrained_model": anomaly_detector._pretrained_model is not None,
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
