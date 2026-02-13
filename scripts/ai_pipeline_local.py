#!/usr/bin/env python3
"""Local end-to-end AI pipeline runner without model training."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.append(str(SCRIPTS_DIR))
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))
sys.path.append(str(ROOT / "services/anomaly-detection-service/src"))
sys.path.append(str(ROOT / "services/fuzzy-inference-service/src"))
sys.path.append(str(ROOT / "services/health-score-service/src"))

from anomaly_detection.config import Settings as AnomalySettings
from anomaly_detection.engine import AnomalyDetector
from dataset_adapters import load_canonical_records, records_to_dicts
from fuzzy_inference.config import Settings as FuzzySettings
from fuzzy_inference.engine import MamdaniFuzzyEngine
from health_score.engine import OutputComposer
from lstm_forecast.config import Settings as ForecastSettings
from lstm_forecast.predictor import PredictorFactory, SurrogateLSTMPredictor
from lstm_forecast.preprocessing import SensorNormalizer, SequenceBuilder


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_optional_context(latest: dict) -> tuple[float, float]:
    traffic_density = _clamp(float(latest.get("traffic_density", 0.0) or 0.0))
    rainfall_raw = float(latest.get("rainfall_intensity", 0.0) or 0.0)
    rainfall_intensity = _clamp(rainfall_raw / 100.0)
    return traffic_density, rainfall_intensity


def run_pipeline(asset_id: str, history: list[dict]) -> dict:
    forecast_settings = ForecastSettings()
    normalizer = SensorNormalizer(forecast_settings)
    sequence_builder = SequenceBuilder(forecast_settings, normalizer)
    try:
        predictor = PredictorFactory.create(forecast_settings)
    except Exception:
        predictor = SurrogateLSTMPredictor()

    anomaly_detector = AnomalyDetector(AnomalySettings())
    fuzzy_engine = MamdaniFuzzyEngine(FuzzySettings())
    output_composer = OutputComposer()

    sequence = sequence_builder.build_last_48h_sequence(history)
    forecast_result = predictor.predict(sequence)

    latest = history[-1]
    latest_norm = normalizer.normalize_record(latest)
    baseline_norm = [normalizer.normalize_record(point) for point in history[:-1]]

    anomaly_result = anomaly_detector.detect(
        current=latest_norm,
        baseline_window=baseline_norm,
    )

    traffic_density, rainfall_intensity = _normalize_optional_context(latest)
    fuzzy_result = fuzzy_engine.evaluate(
        {
            "strain": latest_norm["strain"],
            "vibration": latest_norm["vibration"],
            "temperature": latest_norm["temperature"],
            "rainfall_intensity": rainfall_intensity,
            "traffic_density": traffic_density,
            "failure_probability": forecast_result.failure_probability,
            "anomaly_score": anomaly_result.anomaly_score,
        }
    )

    final_output = output_composer.compose(fuzzy_result.final_risk_score)

    return {
        "asset_id": asset_id,
        "health_score": final_output.health_score,
        "failure_probability_72h": forecast_result.failure_probability,
        "anomaly_flag": anomaly_result.anomaly_flag,
        "risk_level": final_output.risk_level,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "debug": {
            "time_steps_used": len(sequence),
            "anomaly_score": anomaly_result.anomaly_score,
            "final_risk_score": fuzzy_result.final_risk_score,
        },
    }


def _sample_history(points: int = 40) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    records = []
    for i in range(points):
        records.append(
            {
                "strain_value": 220 + (i * 6),
                "vibration_rms": 0.8 + (i * 0.02),
                "temperature": 25 + (i * 0.06),
                "humidity": 50 + (i * 0.25),
                "traffic_density": 0.65,
                "rainfall_intensity": 15.0,
                "timestamp": (now - timedelta(minutes=(points - i) * 10)).isoformat(),
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local AI pipeline")
    parser.add_argument("--asset-id", default="asset_w12_bridge_42")
    parser.add_argument("--dataset", default=None, help="Optional path to dataset CSV")
    parser.add_argument(
        "--kind",
        default="auto",
        choices=["auto", "bridge", "digital_twin", "bearing"],
        help="Dataset kind when using --dataset",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows from dataset")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dataset:
        records, summary = load_canonical_records(
            dataset_path=args.dataset,
            dataset_kind=args.kind,
            limit=args.limit,
        )
        history = records_to_dicts(records)
        if len(history) < 16:
            raise SystemExit("Need at least 16 rows after conversion for AI pipeline run")
        payload = run_pipeline(args.asset_id, history)
        payload["dataset_summary"] = {
            "dataset_path": summary.dataset_path,
            "dataset_kind": summary.dataset_kind,
            "rows_loaded": summary.rows_loaded,
            "started_at": summary.started_at,
            "ended_at": summary.ended_at,
        }
    else:
        payload = run_pipeline(args.asset_id, _sample_history())

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
