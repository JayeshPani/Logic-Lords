"""E2E test: AI scoring -> orchestration -> report -> notification -> blockchain confirmation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]

for rel in [
    "services/fuzzy-inference-service/src",
    "services/lstm-forecast-service/src",
    "services/anomaly-detection-service/src",
    "services/health-score-service/src",
    "apps/orchestration-service/src",
    "services/report-generation-service/src",
    "apps/notification-service/src",
    "services/blockchain-verification-service/src",
]:
    sys.path.append(str(ROOT / rel))

from fuzzy_inference.main import app as fuzzy_app  # noqa: E402
from lstm_forecast.main import app as forecast_app  # noqa: E402
from anomaly_detection.main import app as anomaly_app  # noqa: E402
from health_score.main import app as health_app  # noqa: E402
from health_score.observability import get_metrics as health_metrics  # noqa: E402
from orchestration_service.main import app as orchestration_app  # noqa: E402
from orchestration_service.observability import get_metrics as orchestration_metrics  # noqa: E402
from orchestration_service.routes import _engine as orchestration_engine  # noqa: E402
from report_generation.main import app as report_app  # noqa: E402
from report_generation.observability import get_metrics as report_metrics  # noqa: E402
from report_generation.routes import _engine as report_engine  # noqa: E402
from notification_service.main import app as notification_app  # noqa: E402
from notification_service.observability import get_metrics as notification_metrics  # noqa: E402
from notification_service.routes import _engine as notification_engine  # noqa: E402
from blockchain_verification.main import app as verification_app  # noqa: E402
from blockchain_verification.observability import get_metrics as verification_metrics  # noqa: E402
from blockchain_verification.routes import _engine as verification_engine  # noqa: E402


def _reset_state() -> None:
    health_metrics().reset()
    orchestration_engine.reset_state_for_tests()
    orchestration_metrics().reset()
    report_engine.reset_state_for_tests()
    report_metrics().reset()
    notification_engine.reset_state_for_tests()
    notification_metrics().reset()
    verification_engine.reset_state_for_tests()
    verification_metrics().reset()


def _history(now: datetime) -> list[dict]:
    points = []
    start = now - timedelta(hours=8)
    for idx in range(20):
        timestamp = start + timedelta(minutes=24 * idx)
        points.append(
            {
                "strain_value": 1450.0 + (idx * 8.0),
                "vibration_rms": 6.1 + (idx * 0.03),
                "temperature": 54.0 + (idx * 0.05),
                "humidity": 72.0,
                "traffic_density": 0.88,
                "rainfall_intensity": 0.22,
                "timestamp": timestamp.isoformat(),
            }
        )
    return points


def test_city_risk_to_blockchain_e2e_pipeline() -> None:
    _reset_state()

    fuzzy = TestClient(fuzzy_app)
    forecast = TestClient(forecast_app)
    anomaly = TestClient(anomaly_app)
    health = TestClient(health_app)
    orchestration = TestClient(orchestration_app)
    report = TestClient(report_app)
    notification = TestClient(notification_app)
    verification = TestClient(verification_app)

    now = datetime.now(tz=timezone.utc)
    asset_id = "asset_w12_bridge_0042"

    forecast_response = forecast.post(
        "/forecast",
        json={
            "asset_id": asset_id,
            "history": _history(now),
            "horizon_hours": 72,
        },
        headers={"x-trace-id": "trace-e2e-forecast-001"},
    )
    assert forecast_response.status_code == 200
    forecast_data = forecast_response.json()["data"]

    anomaly_response = anomaly.post(
        "/detect",
        json={
            "asset_id": asset_id,
            "current": {
                "strain": 0.92,
                "vibration": 0.89,
                "temperature": 0.81,
                "humidity": 0.76,
            },
            "baseline_window": [
                {"strain": 0.35, "vibration": 0.31, "temperature": 0.29, "humidity": 0.44},
                {"strain": 0.33, "vibration": 0.30, "temperature": 0.27, "humidity": 0.43},
                {"strain": 0.36, "vibration": 0.32, "temperature": 0.28, "humidity": 0.45},
            ],
        },
        headers={"x-trace-id": "trace-e2e-anomaly-001"},
    )
    assert anomaly_response.status_code == 200
    anomaly_data = anomaly_response.json()["data"]

    fuzzy_response = fuzzy.post(
        "/infer",
        json={
            "asset_id": asset_id,
            "inputs": {
                "strain": 0.88,
                "vibration": 0.84,
                "temperature": 0.79,
                "rainfall_intensity": 0.41,
                "traffic_density": 0.91,
                "failure_probability": forecast_data["failure_probability_72h"],
                "anomaly_score": anomaly_data["anomaly_score"],
            },
        },
        headers={"x-trace-id": "trace-e2e-fuzzy-001"},
    )
    assert fuzzy_response.status_code == 200
    fuzzy_data = fuzzy_response.json()["data"]

    health_response = health.post(
        "/compose",
        json={
            "asset_id": asset_id,
            "final_risk_score": fuzzy_data["final_risk_score"],
            "failure_probability_72h": forecast_data["failure_probability_72h"],
            "anomaly_flag": anomaly_data["anomaly_flag"],
            "timestamp": now.isoformat(),
        },
        headers={"x-trace-id": "trace-e2e-health-001"},
    )
    assert health_response.status_code == 200
    health_data = health_response.json()

    forecast_event = {
        "event_id": str(uuid4()),
        "event_type": "asset.failure.predicted",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "services/lstm-forecast-service",
        "trace_id": "trace-e2e-orch-forecast-001",
        "data": {
            "asset_id": asset_id,
            "generated_at": forecast_data["generated_at"],
            "horizon_hours": 72,
            "failure_probability_72h": forecast_data["failure_probability_72h"],
            "confidence": forecast_data["confidence"],
        },
    }
    assert orchestration.post("/events/asset-failure-predicted", json=forecast_event).status_code == 200

    risk_event = {
        "event_id": str(uuid4()),
        "event_type": "asset.risk.computed",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "services/health-score-service",
        "trace_id": "trace-e2e-orch-risk-001",
        "data": {
            "asset_id": asset_id,
            "evaluated_at": health_data["timestamp"],
            "health_score": health_data["health_score"],
            "risk_level": health_data["risk_level"],
            "failure_probability_72h": health_data["failure_probability_72h"],
            "anomaly_flag": health_data["anomaly_flag"],
        },
    }

    workflow_response = orchestration.post("/events/asset-risk-computed", json=risk_event)
    assert workflow_response.status_code == 200
    workflow_body = workflow_response.json()
    assert workflow_body["workflow_triggered"] is True
    workflow_id = workflow_body["workflow_id"]

    maintenance_response = orchestration.post(
        f"/workflows/{workflow_id}/maintenance/completed",
        json={"performed_by": "team-alpha", "summary": "priority repair completed"},
    )
    assert maintenance_response.status_code == 200

    inspection_event = workflow_body["inspection_requested_event"]
    maintenance_event = maintenance_response.json()["maintenance_completed_event"]

    assert report.post("/events/inspection-requested", json=inspection_event).status_code == 200
    assert report.post("/events/maintenance-completed", json=maintenance_event).status_code == 200

    report_command = {
        "command_id": str(uuid4()),
        "command_type": "report.generate",
        "command_version": "v1",
        "requested_at": (now + timedelta(minutes=1)).isoformat(),
        "requested_by": "services/report-generation-service",
        "trace_id": "trace-e2e-report-001",
        "payload": {
            "maintenance_id": maintenance_event["data"]["maintenance_id"],
            "asset_id": asset_id,
            "report_type": "maintenance_verification",
            "include_sensor_window": {
                "from": (now - timedelta(hours=2)).isoformat(),
                "to": now.isoformat(),
            },
        },
    }

    report_response = report.post("/generate", json={"command": report_command})
    assert report_response.status_code == 200
    report_body = report_response.json()

    notify_response = notification.post(
        "/dispatch",
        json={
            "command_id": str(uuid4()),
            "command_type": "notification.dispatch",
            "command_version": "v1",
            "requested_at": (now + timedelta(minutes=2)).isoformat(),
            "requested_by": "apps/orchestration-service",
            "trace_id": "trace-e2e-notify-001",
            "payload": {
                "channel": "email",
                "recipient": "ops@infraguard.city",
                "message": "Maintenance workflow completed and verification in progress",
                "severity": "warning",
                "context": {
                    "asset_id": asset_id,
                    "risk_level": health_data["risk_level"],
                    "ticket_id": inspection_event["data"]["ticket_id"],
                },
            },
        },
    )
    assert notify_response.status_code == 200
    assert notify_response.json()["dispatch"]["status"] == "delivered"

    verification_command = report_body["verification_record_command"]
    record_response = verification.post("/record", json=verification_command)
    assert record_response.status_code == 200

    maintenance_id = verification_command["payload"]["maintenance_id"]
    assert verification.post(f"/verifications/{maintenance_id}/track").status_code == 200
    assert verification.post(f"/verifications/{maintenance_id}/track").status_code == 200
    final_track = verification.post(f"/verifications/{maintenance_id}/track")

    assert final_track.status_code == 200
    final_body = final_track.json()
    assert final_body["verification"]["verification_status"] == "confirmed"
    assert final_body["maintenance_verified_event"]["event_type"] == "maintenance.verified.blockchain"
