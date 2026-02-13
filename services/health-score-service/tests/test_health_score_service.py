"""Tests for health score service."""

from fastapi.testclient import TestClient

from health_score.engine import OutputComposer
from health_score.main import app


def test_composer_maps_ranges_to_levels() -> None:
    composer = OutputComposer()
    assert composer.compose(0.1).risk_level == "Very Low"
    assert composer.compose(0.35).risk_level == "Low"
    assert composer.compose(0.55).risk_level == "Moderate"
    assert composer.compose(0.75).risk_level == "High"
    assert composer.compose(0.95).risk_level == "Critical"


def test_compose_endpoint_shape() -> None:
    client = TestClient(app)
    response = client.post(
        "/compose",
        json={
            "asset_id": "asset_w12_bridge_42",
            "final_risk_score": 0.73,
            "failure_probability_72h": 0.65,
            "anomaly_flag": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["health_score"] == 0.73
    assert body["risk_level"] == "High"
