"""Tests for report generation service."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from report_generation.main import app
from report_generation.observability import get_metrics
from report_generation.routes import _engine


def _inspection_event(*, asset_id: str = "asset_w12_bridge_0042") -> dict:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "event_id": str(uuid4()),
        "event_type": "inspection.requested",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "apps/orchestration-service",
        "trace_id": "trace-report-inspection-001",
        "data": {
            "ticket_id": "insp_20260214_0001",
            "asset_id": asset_id,
            "requested_at": now,
            "priority": "high",
            "reason": "risk level high and anomaly flag detected",
        },
    }


def _maintenance_event(
    *,
    maintenance_id: str = "mnt_20260214_0001",
    asset_id: str = "asset_w12_bridge_0042",
) -> dict:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "event_id": str(uuid4()),
        "event_type": "maintenance.completed",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "apps/orchestration-service",
        "trace_id": "trace-report-maintenance-001",
        "data": {
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "completed_at": now,
            "performed_by": "team-alpha",
            "summary": "replaced damaged expansion joint and re-sealed surface",
        },
    }


def _generate_command(
    *,
    maintenance_id: str = "mnt_20260214_0001",
    asset_id: str = "asset_w12_bridge_0042",
    report_type: str = "maintenance_verification",
) -> dict:
    now = datetime.now(tz=timezone.utc)
    earlier = now - timedelta(hours=2)
    return {
        "command": {
            "command_id": str(uuid4()),
            "command_type": "report.generate",
            "command_version": "v1",
            "requested_at": now.isoformat(),
            "requested_by": "services/report-generation-service",
            "trace_id": "trace-report-generate-001",
            "payload": {
                "maintenance_id": maintenance_id,
                "asset_id": asset_id,
                "report_type": report_type,
                "include_sensor_window": {
                    "from": earlier.isoformat(),
                    "to": now.isoformat(),
                },
            },
        }
    }


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    _engine.reset_state_for_tests()
    get_metrics().reset()


def test_generate_report_returns_bundle_and_messages() -> None:
    client = TestClient(app)

    assert client.post("/events/inspection-requested", json=_inspection_event()).status_code == 200
    assert client.post("/events/maintenance-completed", json=_maintenance_event()).status_code == 200

    response = client.post("/generate", json=_generate_command())
    assert response.status_code == 200
    body = response.json()

    assert body["report_bundle"]["report_id"].startswith("rpt_")
    assert body["report_bundle"]["evidence_hash"].startswith("0x")
    assert len(body["report_bundle"]["evidence_hash"]) == 66

    assert body["report_generated_event"]["event_type"] == "report.generated"
    assert body["verification_record_command"]["command_type"] == "verification.record.blockchain"


def test_generate_requires_maintenance_context() -> None:
    client = TestClient(app)

    response = client.post("/generate", json=_generate_command())
    assert response.status_code == 404
    assert "maintenance context not found" in response.json()["detail"]


def test_metrics_track_context_and_generation() -> None:
    client = TestClient(app)

    before = client.get("/metrics")
    assert before.status_code == 200
    assert "infraguard_report_generation_requests_total 0" in before.text

    assert client.post("/events/inspection-requested", json=_inspection_event()).status_code == 200
    assert client.post("/events/maintenance-completed", json=_maintenance_event()).status_code == 200
    assert client.post("/generate", json=_generate_command()).status_code == 200

    after = client.get("/metrics")
    assert after.status_code == 200
    assert "infraguard_report_generation_requests_total 1" in after.text
    assert "infraguard_report_generation_success_total 1" in after.text
    assert "infraguard_report_generation_errors_total 0" in after.text
    assert "infraguard_report_generation_inspection_context_events_total 1" in after.text
    assert "infraguard_report_generation_maintenance_context_events_total 1" in after.text
