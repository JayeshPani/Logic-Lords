"""Tests for fuzzy inference service."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from fuzzy_inference.config import Settings
from fuzzy_inference.engine import MamdaniFuzzyEngine
from fuzzy_inference.events import build_asset_risk_computed_event
from fuzzy_inference.main import app
from fuzzy_inference.observability import get_metrics


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    get_metrics().reset()


def test_fuzzy_low_inputs_produce_low_risk() -> None:
    engine = MamdaniFuzzyEngine(Settings())
    result = engine.evaluate(
        {
            "strain": 0.08,
            "vibration": 0.10,
            "temperature": 0.15,
            "rainfall_intensity": 0.05,
            "traffic_density": 0.12,
            "failure_probability": 0.10,
            "anomaly_score": 0.08,
        }
    )
    assert result.final_risk_score <= 0.4
    assert result.risk_level in ["Very Low", "Low"]


def test_fuzzy_high_inputs_produce_critical_risk() -> None:
    engine = MamdaniFuzzyEngine(Settings())
    result = engine.evaluate(
        {
            "strain": 0.92,
            "vibration": 0.95,
            "temperature": 0.93,
            "rainfall_intensity": 0.88,
            "traffic_density": 0.9,
            "failure_probability": 0.91,
            "anomaly_score": 0.94,
        }
    )
    assert result.final_risk_score >= 0.75
    assert result.risk_level in ["High", "Critical"]


def test_infer_endpoint_returns_expected_shape() -> None:
    client = TestClient(app)
    response = client.post(
        "/infer",
        json={
            "asset_id": "asset_w12_bridge_42",
            "inputs": {
                "strain": 0.74,
                "vibration": 0.62,
                "temperature": 0.68,
                "rainfall_intensity": 0.45,
                "traffic_density": 0.81,
                "failure_probability": 0.65,
                "anomaly_score": 0.29,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["asset_id"] == "asset_w12_bridge_42"
    assert 0 <= body["data"]["final_risk_score"] <= 1
    assert body["data"]["method"] == "mamdani_centroid"


def test_metrics_endpoint_tracks_inference_calls() -> None:
    client = TestClient(app)
    before = client.get("/metrics")
    assert before.status_code == 200
    assert "infraguard_fuzzy_infer_requests_total 0" in before.text

    response = client.post(
        "/infer",
        json={
            "asset_id": "asset_w12_bridge_42",
            "inputs": {
                "strain": 0.74,
                "vibration": 0.62,
                "temperature": 0.68,
                "rainfall_intensity": 0.45,
                "traffic_density": 0.81,
                "failure_probability": 0.65,
                "anomaly_score": 0.29,
            },
        },
        headers={"x-trace-id": "trace-metrics-001"},
    )
    assert response.status_code == 200

    after = client.get("/metrics")
    assert after.status_code == 200
    assert "infraguard_fuzzy_infer_requests_total 1" in after.text
    assert "infraguard_fuzzy_infer_success_total 1" in after.text
    assert "infraguard_fuzzy_infer_errors_total 0" in after.text


def test_asset_risk_event_builder_outputs_contract_shape() -> None:
    event = build_asset_risk_computed_event(
        asset_id="asset_w12_bridge_42",
        evaluated_at=datetime.now(tz=timezone.utc),
        health_score=0.83,
        risk_level="High",
        failure_probability_72h=0.65,
        anomaly_score=0.72,
        anomaly_threshold=0.7,
        trace_id="trace-event-0001",
        produced_by="services/fuzzy-inference-service",
    )
    assert event["event_type"] == "asset.risk.computed"
    assert event["data"]["anomaly_flag"] == 1
    assert event["data"]["health_score"] == 0.83
