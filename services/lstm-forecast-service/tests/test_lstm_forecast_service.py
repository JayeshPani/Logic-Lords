"""Tests for forecast service."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from lstm_forecast.config import Settings
from lstm_forecast.predictor import SurrogateLSTMPredictor
from lstm_forecast.preprocessing import SensorNormalizer, SequenceBuilder
from lstm_forecast.main import app


def _history(points: int, aggressive: bool) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    records: list[dict] = []
    for index in range(points):
        records.append(
            {
                "timestamp": (now - timedelta(minutes=(points - index) * 10)).isoformat(),
                "strain_value": 200 + (index * (35 if aggressive else 2)),
                "vibration_rms": 0.8 + (index * (0.12 if aggressive else 0.005)),
                "temperature": 24 + (index * (0.7 if aggressive else 0.02)),
                "humidity": 52 + (index * (1.1 if aggressive else 0.03)),
                "traffic_density": 0.6,
                "rainfall_intensity": 0.3,
            }
        )
    return records


def test_normalizer_scales_to_zero_one() -> None:
    settings = Settings()
    normalizer = SensorNormalizer(settings)
    normalized = normalizer.normalize_record(
        {
            "timestamp": datetime.now(tz=timezone.utc),
            "strain_value": 1000,
            "vibration_rms": 5,
            "temperature": 30,
            "humidity": 70,
        }
    )
    for value in normalized.values():
        assert 0 <= value <= 1


def test_sequence_builder_enforces_window_and_min_points() -> None:
    settings = Settings(min_sequence_points=5)
    builder = SequenceBuilder(settings, SensorNormalizer(settings))
    sequence = builder.build_last_48h_sequence(_history(12, aggressive=False))
    assert len(sequence) >= 5


def test_surrogate_predictor_detects_aggressive_trend() -> None:
    settings = Settings(min_sequence_points=5)
    builder = SequenceBuilder(settings, SensorNormalizer(settings))
    predictor = SurrogateLSTMPredictor()

    low = predictor.predict(builder.build_last_48h_sequence(_history(12, aggressive=False)))
    high = predictor.predict(builder.build_last_48h_sequence(_history(12, aggressive=True)))
    assert high.failure_probability > low.failure_probability


def test_forecast_endpoint_happy_path() -> None:
    client = TestClient(app)
    response = client.post(
        "/forecast",
        json={
            "asset_id": "asset_w12_bridge_42",
            "horizon_hours": 72,
            "history": _history(20, aggressive=True),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["data"]["failure_probability_72h"] <= 1
    assert body["data"]["normalized"] is True


def test_forecast_rejects_short_history() -> None:
    client = TestClient(app)
    response = client.post(
        "/forecast",
        json={
            "asset_id": "asset_w12_bridge_42",
            "horizon_hours": 72,
            "history": _history(3, aggressive=False),
        },
    )
    assert response.status_code == 422
