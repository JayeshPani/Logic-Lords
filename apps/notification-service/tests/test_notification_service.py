"""Tests for notification service."""

from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from notification_service.main import app  # noqa: E402
from notification_service.observability import get_metrics  # noqa: E402
from notification_service.routes import _engine  # noqa: E402


def _command(
    *,
    channel: str = "email",
    severity: str = "warning",
    fallback_channels: list[str] | None = None,
) -> dict:
    payload: dict[str, object] = {
        "channel": channel,
        "recipient": "field-team@infraguard.city",
        "message": "Bridge segment risk crossed threshold",
        "severity": severity,
        "context": {
            "asset_id": "asset_w12_bridge_0042",
            "risk_level": "High",
            "ticket_id": "insp_20260214_0009",
        },
    }
    if fallback_channels is not None:
        payload["fallback_channels"] = fallback_channels

    return {
        "command_id": str(uuid4()),
        "command_type": "notification.dispatch",
        "command_version": "v1",
        "requested_at": "2026-02-14T04:00:00+00:00",
        "requested_by": "apps/orchestration-service",
        "trace_id": "trace-notification-12345",
        "payload": payload,
    }


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    _engine.reset_state_for_tests()
    get_metrics().reset()


def test_dispatch_success_on_primary_channel() -> None:
    client = TestClient(app)

    response = client.post("/dispatch", json=_command(channel="sms", severity="watch"))
    assert response.status_code == 200
    body = response.json()

    assert body["dispatch"]["status"] == "delivered"
    assert body["dispatch"]["primary_channel"] == "sms"
    assert body["dispatch"]["final_channel"] == "sms"
    assert body["dispatch"]["attempts_total"] == 1
    assert body["dispatch"]["fallback_used"] is False
    assert body["delivery_status_event"]["event_type"] == "notification.delivery.status"


def test_dispatch_retries_then_succeeds_on_same_channel() -> None:
    client = TestClient(app)

    def flaky_email_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, context
        if attempt < 2:
            return False, "smtp timeout"
        return True, None

    _engine.set_channel_dispatcher_for_tests("email", flaky_email_dispatcher)

    response = client.post("/dispatch", json=_command(channel="email", severity="warning"))
    assert response.status_code == 200
    body = response.json()

    assert body["dispatch"]["status"] == "delivered"
    assert body["dispatch"]["final_channel"] == "email"
    assert body["dispatch"]["attempts_total"] == 2
    assert body["dispatch"]["retries_used"] == 1
    assert body["dispatch"]["fallback_used"] is False


def test_dispatch_falls_back_to_secondary_channel() -> None:
    client = TestClient(app)

    def fail_sms_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, attempt, context
        return False, "sms gateway unavailable"

    _engine.set_channel_dispatcher_for_tests("sms", fail_sms_dispatcher)

    response = client.post("/dispatch", json=_command(channel="sms", severity="critical"))
    assert response.status_code == 200
    body = response.json()

    assert body["dispatch"]["status"] == "delivered"
    assert body["dispatch"]["final_channel"] == "chat"
    assert body["dispatch"]["fallback_used"] is True
    assert body["dispatch"]["attempts_total"] == 4
    assert body["dispatch"]["retries_used"] == 2


def test_dispatch_uses_payload_fallback_order() -> None:
    client = TestClient(app)

    def fail_sms_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, attempt, context
        return False, "sms gateway unavailable"

    _engine.set_channel_dispatcher_for_tests("sms", fail_sms_dispatcher)

    response = client.post(
        "/dispatch",
        json=_command(channel="sms", severity="critical", fallback_channels=["webhook", "email"]),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["dispatch"]["status"] == "delivered"
    assert body["dispatch"]["primary_channel"] == "sms"
    assert body["dispatch"]["final_channel"] == "webhook"
    assert body["dispatch"]["fallback_used"] is True
    assert body["dispatch"]["channels_tried"][:2] == ["sms", "webhook"]


def test_dispatch_fails_after_all_channels_and_retries_exhausted() -> None:
    client = TestClient(app)

    def fail_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, attempt, context
        return False, "adapter offline"

    for channel in ("email", "sms", "webhook", "chat"):
        _engine.set_channel_dispatcher_for_tests(channel, fail_dispatcher)

    response = client.post("/dispatch", json=_command(channel="webhook", severity="critical"))
    assert response.status_code == 200
    body = response.json()

    assert body["dispatch"]["status"] == "failed"
    assert body["dispatch"]["attempts_total"] == 12
    assert body["dispatch"]["retries_used"] == 8
    assert body["dispatch"]["fallback_used"] is True
    assert body["delivery_status_event"]["data"]["status"] == "failed"


def test_dispatch_status_api_and_metrics() -> None:
    client = TestClient(app)

    first = client.post("/dispatch", json=_command(channel="chat", severity="healthy"))
    assert first.status_code == 200
    first_dispatch_id = first.json()["dispatch"]["dispatch_id"]

    def fail_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, attempt, context
        return False, "network blocked"

    for channel in ("email", "sms", "webhook", "chat"):
        _engine.set_channel_dispatcher_for_tests(channel, fail_dispatcher)

    second = client.post("/dispatch", json=_command(channel="email", severity="critical"))
    assert second.status_code == 200

    single = client.get(f"/dispatches/{first_dispatch_id}")
    assert single.status_code == 200
    assert single.json()["dispatch_id"] == first_dispatch_id

    all_items = client.get("/dispatches")
    assert all_items.status_code == 200
    assert len(all_items.json()["items"]) == 2

    failed_items = client.get("/dispatches", params={"status": "failed"})
    assert failed_items.status_code == 200
    assert len(failed_items.json()["items"]) == 1

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "infraguard_notification_dispatch_requests_total 2" in metrics.text
    assert "infraguard_notification_dispatch_delivered_total 1" in metrics.text
    assert "infraguard_notification_dispatch_failed_total 1" in metrics.text
