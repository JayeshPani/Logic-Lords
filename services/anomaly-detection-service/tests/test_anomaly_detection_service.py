"""Tests for anomaly detection service."""

from fastapi.testclient import TestClient

from anomaly_detection.config import Settings
from anomaly_detection.engine import AnomalyDetector
from anomaly_detection.main import app


def _baseline(n: int) -> list[dict]:
    return [
        {
            "strain": 0.2 + (0.01 * (i % 3)),
            "vibration": 0.25 + (0.01 * (i % 2)),
            "temperature": 0.35 + (0.01 * (i % 4)),
            "humidity": 0.45 + (0.01 * (i % 3)),
        }
        for i in range(n)
    ]


def test_detector_flags_high_anomaly() -> None:
    detector = AnomalyDetector(Settings(min_baseline_points=8, anomaly_threshold=0.6))
    result = detector.detect(
        current={"strain": 0.98, "vibration": 0.95, "temperature": 0.90, "humidity": 0.85},
        baseline_window=_baseline(20),
    )
    assert result.anomaly_score >= 0.6
    assert result.anomaly_flag == 1


def test_detector_low_signal_is_not_anomaly() -> None:
    detector = AnomalyDetector(Settings(min_baseline_points=8, anomaly_threshold=0.75))
    result = detector.detect(
        current={"strain": 0.2, "vibration": 0.22, "temperature": 0.35, "humidity": 0.45},
        baseline_window=_baseline(20),
    )
    assert result.anomaly_score < 0.75


def test_detect_endpoint_shape() -> None:
    client = TestClient(app)
    response = client.post(
        "/detect",
        json={
            "asset_id": "asset_w12_bridge_42",
            "current": {"strain": 0.78, "vibration": 0.82, "temperature": 0.64, "humidity": 0.55},
            "baseline_window": _baseline(24),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["asset_id"] == "asset_w12_bridge_42"
    assert body["data"]["anomaly_flag"] in [0, 1]
