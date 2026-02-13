"""Tests for health score service."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from health_score.engine import OutputComposer
from health_score.events import build_asset_risk_computed_event
from health_score.main import app
from health_score.observability import get_metrics


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    get_metrics().reset()


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


def test_metrics_endpoint_tracks_compose_calls() -> None:
    client = TestClient(app)
    before = client.get("/metrics")
    assert before.status_code == 200
    assert "infraguard_health_score_requests_total 0" in before.text

    response = client.post(
        "/compose",
        json={
            "asset_id": "asset_w12_bridge_42",
            "final_risk_score": 0.73,
            "failure_probability_72h": 0.65,
            "anomaly_flag": 0,
        },
        headers={"x-trace-id": "trace-health-metrics-001"},
    )
    assert response.status_code == 200

    after = client.get("/metrics")
    assert after.status_code == 200
    assert "infraguard_health_score_requests_total 1" in after.text
    assert "infraguard_health_score_success_total 1" in after.text
    assert "infraguard_health_score_errors_total 0" in after.text


def test_asset_risk_computed_event_builder() -> None:
    event = build_asset_risk_computed_event(
        asset_id="asset_w12_bridge_42",
        evaluated_at=datetime.now(tz=timezone.utc),
        health_score=0.73,
        risk_level="High",
        failure_probability_72h=0.65,
        anomaly_flag=0,
        trace_id="trace-health-event-0001",
        produced_by="services/health-score-service",
    )
    assert event["event_type"] == "asset.risk.computed"
    assert event["data"]["health_score"] == 0.73
    assert event["data"]["risk_level"] == "High"
