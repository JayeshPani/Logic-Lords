"""Tests for orchestration service workflow behavior."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from orchestration_service.main import app  # noqa: E402
from orchestration_service.observability import get_metrics  # noqa: E402
from orchestration_service.routes import _engine  # noqa: E402


def _risk_event(
    *,
    asset_id: str = "asset_w12_bridge_0042",
    risk_level: str = "High",
    health_score: float = 0.82,
    failure_probability_72h: float = 0.74,
    anomaly_flag: int = 1,
) -> dict:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "event_id": str(uuid4()),
        "event_type": "asset.risk.computed",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "services/health-score-service",
        "trace_id": "trace-orch-risk-0001",
        "data": {
            "asset_id": asset_id,
            "evaluated_at": now,
            "health_score": health_score,
            "risk_level": risk_level,
            "failure_probability_72h": failure_probability_72h,
            "anomaly_flag": anomaly_flag,
        },
    }


def _forecast_event(*, asset_id: str = "asset_w12_bridge_0042", failure_probability_72h: float = 0.92) -> dict:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "event_id": str(uuid4()),
        "event_type": "asset.failure.predicted",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "services/lstm-forecast-service",
        "trace_id": "trace-orch-forecast-001",
        "data": {
            "asset_id": asset_id,
            "generated_at": now,
            "horizon_hours": 72,
            "failure_probability_72h": failure_probability_72h,
            "confidence": 0.77,
        },
    }


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    _engine.reset_state_for_tests()
    get_metrics().reset()


def test_high_risk_event_starts_workflow_and_emits_inspection_requested() -> None:
    client = TestClient(app)

    response = client.post("/events/asset-risk-computed", json=_risk_event())
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_triggered"] is True
    assert body["workflow_status"] == "inspection_requested"
    assert body["inspection_requested_event"]["event_type"] == "inspection.requested"
    assert body["inspection_create_command"]["command_type"] == "inspection.create"

    workflow_id = body["workflow_id"]
    assert workflow_id

    state = client.get(f"/workflows/{workflow_id}")
    assert state.status_code == 200
    state_body = state.json()
    assert state_body["status"] == "inspection_requested"
    assert state_body["inspection_ticket_id"].startswith("insp_")


def test_low_risk_event_is_ignored() -> None:
    client = TestClient(app)

    response = client.post(
        "/events/asset-risk-computed",
        json=_risk_event(risk_level="Low", health_score=0.2, failure_probability_72h=0.12, anomaly_flag=0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_triggered"] is False
    assert body.get("workflow_id") is None
    assert body.get("workflow_status") is None
    assert body.get("inspection_requested_event") is None


def test_forecast_context_can_trigger_workflow() -> None:
    client = TestClient(app)

    forecast_response = client.post("/events/asset-failure-predicted", json=_forecast_event())
    assert forecast_response.status_code == 200

    response = client.post(
        "/events/asset-risk-computed",
        json=_risk_event(risk_level="Moderate", health_score=0.45, failure_probability_72h=0.20, anomaly_flag=0),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_triggered"] is True
    assert body["workflow_status"] == "inspection_requested"


def test_retry_policy_eventually_succeeds() -> None:
    client = TestClient(app)

    attempts = {"count": 0}

    def flaky_dispatcher(command: dict, attempt: int) -> tuple[bool, str | None]:
        del command
        attempts["count"] += 1
        if attempt < 3:
            return False, "temporary queue timeout"
        return True, None

    _engine.set_inspection_dispatcher_for_tests(flaky_dispatcher)

    response = client.post("/events/asset-risk-computed", json=_risk_event())
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_triggered"] is True
    assert body["workflow_status"] == "inspection_requested"
    assert body["retries_used"] == 2
    assert attempts["count"] == 3

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "infraguard_orchestration_retries_total 2" in metrics.text


def test_workflow_fails_after_exhausting_retries() -> None:
    client = TestClient(app)

    def always_fail_dispatcher(command: dict, attempt: int) -> tuple[bool, str | None]:
        del command, attempt
        return False, "downstream inspection queue unavailable"

    _engine.set_inspection_dispatcher_for_tests(always_fail_dispatcher)

    response = client.post("/events/asset-risk-computed", json=_risk_event())
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_triggered"] is True
    assert body["workflow_status"] == "failed"
    assert body.get("inspection_requested_event") is None

    workflow_id = body["workflow_id"]
    state = client.get(f"/workflows/{workflow_id}")
    assert state.status_code == 200
    assert state.json()["status"] == "failed"


def test_complete_maintenance_publishes_event_and_updates_workflow() -> None:
    client = TestClient(app)

    start = client.post("/events/asset-risk-computed", json=_risk_event())
    assert start.status_code == 200
    workflow_id = start.json()["workflow_id"]

    complete = client.post(
        f"/workflows/{workflow_id}/maintenance/completed",
        json={"performed_by": "team-alpha", "summary": "replaced expansion joint"},
    )
    assert complete.status_code == 200
    body = complete.json()
    assert body["workflow_status"] == "maintenance_completed"
    assert body["maintenance_completed_event"]["event_type"] == "maintenance.completed"

    state = client.get(f"/workflows/{workflow_id}")
    assert state.status_code == 200
    assert state.json()["status"] == "maintenance_completed"
