"""Performance smoke tests for critical service paths."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import statistics
import sys
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]

for rel in [
    "services/health-score-service/src",
    "apps/notification-service/src",
]:
    sys.path.append(str(ROOT / rel))

from health_score.main import app as health_app  # noqa: E402
from health_score.observability import get_metrics as health_metrics  # noqa: E402
from notification_service.main import app as notification_app  # noqa: E402
from notification_service.observability import get_metrics as notification_metrics  # noqa: E402
from notification_service.routes import _engine as notification_engine  # noqa: E402


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]


def test_service_latency_smoke() -> None:
    health_metrics().reset()
    notification_engine.reset_state_for_tests()
    notification_metrics().reset()

    health = TestClient(health_app)
    notification = TestClient(notification_app)

    compose_latencies_ms: list[float] = []
    for _ in range(80):
        started = perf_counter()
        response = health.post(
            "/compose",
            json={
                "asset_id": "asset_w12_bridge_0042",
                "final_risk_score": 0.78,
                "failure_probability_72h": 0.66,
                "anomaly_flag": 1,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        assert response.status_code == 200
        compose_latencies_ms.append(elapsed_ms)

    dispatch_latencies_ms: list[float] = []
    for _ in range(80):
        started = perf_counter()
        response = notification.post(
            "/dispatch",
            json={
                "command_id": str(uuid4()),
                "command_type": "notification.dispatch",
                "command_version": "v1",
                "requested_at": datetime.now(tz=timezone.utc).isoformat(),
                "requested_by": "apps/orchestration-service",
                "trace_id": f"trace-perf-notify-{uuid4().hex[:12]}",
                "payload": {
                    "channel": "chat",
                    "recipient": "ops-room-1",
                    "message": "Performance smoke dispatch",
                    "severity": "watch",
                    "context": {"asset_id": "asset_w12_bridge_0042", "risk_level": "High"},
                },
            },
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        assert response.status_code == 200
        assert response.json()["dispatch"]["status"] == "delivered"
        dispatch_latencies_ms.append(elapsed_ms)

    compose_p95 = _p95(compose_latencies_ms)
    dispatch_p95 = _p95(dispatch_latencies_ms)

    assert compose_p95 < 120.0
    assert dispatch_p95 < 150.0

    # Keep average in check for local runtime smoke targets.
    assert statistics.mean(compose_latencies_ms) < 80.0
    assert statistics.mean(dispatch_latencies_ms) < 90.0
