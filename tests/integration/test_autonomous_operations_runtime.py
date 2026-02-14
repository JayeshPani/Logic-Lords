"""Integration test: orchestration -> report -> notification -> blockchain runtime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]

for rel in [
    "apps/orchestration-service/src",
    "services/report-generation-service/src",
    "apps/notification-service/src",
    "services/blockchain-verification-service/src",
]:
    sys.path.append(str(ROOT / rel))

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
    orchestration_engine.reset_state_for_tests()
    orchestration_metrics().reset()
    report_engine.reset_state_for_tests()
    report_metrics().reset()
    notification_engine.reset_state_for_tests()
    notification_metrics().reset()
    verification_engine.reset_state_for_tests()
    verification_metrics().reset()


def test_autonomous_operations_runtime_flow() -> None:
    _reset_state()

    orchestration = TestClient(orchestration_app)
    report = TestClient(report_app)
    notification = TestClient(notification_app)
    verification = TestClient(verification_app)

    now = datetime.now(tz=timezone.utc)

    forecast_event = {
        "event_id": str(uuid4()),
        "event_type": "asset.failure.predicted",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "services/lstm-forecast-service",
        "trace_id": "trace-int-ops-forecast-001",
        "data": {
            "asset_id": "asset_w12_bridge_0042",
            "generated_at": now.isoformat(),
            "horizon_hours": 72,
            "failure_probability_72h": 0.88,
            "confidence": 0.81,
        },
    }

    risk_event = {
        "event_id": str(uuid4()),
        "event_type": "asset.risk.computed",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "services/health-score-service",
        "trace_id": "trace-int-ops-risk-001",
        "data": {
            "asset_id": "asset_w12_bridge_0042",
            "evaluated_at": now.isoformat(),
            "health_score": 0.83,
            "risk_level": "High",
            "failure_probability_72h": 0.71,
            "anomaly_flag": 1,
        },
    }

    forecast_response = orchestration.post("/events/asset-failure-predicted", json=forecast_event)
    assert forecast_response.status_code == 200

    risk_response = orchestration.post("/events/asset-risk-computed", json=risk_event)
    assert risk_response.status_code == 200
    risk_body = risk_response.json()
    assert risk_body["workflow_triggered"] is True
    assert risk_body["workflow_status"] == "inspection_requested"

    workflow_id = risk_body["workflow_id"]
    inspection_event = risk_body["inspection_requested_event"]

    complete_response = orchestration.post(
        f"/workflows/{workflow_id}/maintenance/completed",
        json={"performed_by": "team-alpha", "summary": "bearing and joint maintenance done"},
    )
    assert complete_response.status_code == 200
    maintenance_event = complete_response.json()["maintenance_completed_event"]

    assert report.post("/events/inspection-requested", json=inspection_event).status_code == 200
    assert report.post("/events/maintenance-completed", json=maintenance_event).status_code == 200

    generated_at = now + timedelta(minutes=2)
    report_command = {
        "command_id": str(uuid4()),
        "command_type": "report.generate",
        "command_version": "v1",
        "requested_at": generated_at.isoformat(),
        "requested_by": "services/report-generation-service",
        "trace_id": "trace-int-ops-report-001",
        "payload": {
            "maintenance_id": maintenance_event["data"]["maintenance_id"],
            "asset_id": maintenance_event["data"]["asset_id"],
            "report_type": "maintenance_verification",
            "include_sensor_window": {
                "from": (generated_at - timedelta(hours=2)).isoformat(),
                "to": generated_at.isoformat(),
            },
        },
    }

    report_response = report.post(
        "/generate",
        json={"command": report_command, "generated_at": generated_at.isoformat()},
    )
    assert report_response.status_code == 200
    report_body = report_response.json()

    notification_command = {
        "command_id": str(uuid4()),
        "command_type": "notification.dispatch",
        "command_version": "v1",
        "requested_at": (generated_at + timedelta(minutes=1)).isoformat(),
        "requested_by": "apps/orchestration-service",
        "trace_id": "trace-int-ops-notification-001",
        "payload": {
            "channel": "email",
            "recipient": "field-team@infraguard.city",
            "message": "Maintenance completed; verification initiated",
            "severity": "warning",
            "context": {
                "asset_id": maintenance_event["data"]["asset_id"],
                "ticket_id": inspection_event["data"]["ticket_id"],
                "risk_level": risk_event["data"]["risk_level"],
            },
        },
    }
    notify_response = notification.post("/dispatch", json=notification_command)
    assert notify_response.status_code == 200
    assert notify_response.json()["dispatch"]["status"] == "delivered"

    verification_command = report_body["verification_record_command"]
    record_response = verification.post("/record", json=verification_command)
    assert record_response.status_code == 200

    verify_maintenance_id = verification_command["payload"]["maintenance_id"]
    track_1 = verification.post(f"/verifications/{verify_maintenance_id}/track")
    track_2 = verification.post(f"/verifications/{verify_maintenance_id}/track")
    track_3 = verification.post(f"/verifications/{verify_maintenance_id}/track")

    assert track_1.status_code == 200
    assert track_2.status_code == 200
    assert track_3.status_code == 200

    final = track_3.json()
    assert final["verification"]["verification_status"] == "confirmed"
    assert final["maintenance_verified_event"]["event_type"] == "maintenance.verified.blockchain"
