"""Tests for API gateway."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from api_gateway.main import app  # noqa: E402
from api_gateway.observability import get_metrics  # noqa: E402
from api_gateway.security import get_rate_limiter  # noqa: E402
from api_gateway.store import get_store  # noqa: E402


AUTH_HEADERS = {"Authorization": "Bearer dev-token", "x-trace-id": "trc_test_gateway_001"}


@pytest.fixture(autouse=True)
def reset_state() -> None:
    get_store().reset()
    get_metrics().reset()
    limiter = get_rate_limiter()
    limiter.set_limits(limit=60, window_seconds=60)


def test_health_is_public() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "api-gateway"
    assert body["status"] == "ok"


def test_assets_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/assets")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_asset_list_and_create_flow() -> None:
    client = TestClient(app)

    listed = client.get("/assets", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) >= 1

    created = client.post(
        "/assets",
        headers=AUTH_HEADERS,
        json={
            "asset_id": "asset_w15_bridge_0901",
            "name": "West Sector Bridge 901",
            "asset_type": "bridge",
            "zone": "w15",
            "location": {"lat": 19.101, "lon": 72.901},
            "metadata": {"lanes": 2},
        },
    )
    assert created.status_code == 201
    created_asset = created.json()["data"]
    assert created_asset["asset_id"] == "asset_w15_bridge_0901"

    fetched = client.get("/assets/asset_w15_bridge_0901", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["name"] == "West Sector Bridge 901"


def test_health_forecast_and_verification_endpoints() -> None:
    client = TestClient(app)

    health = client.get("/assets/asset_w12_bridge_0042/health", headers=AUTH_HEADERS)
    assert health.status_code == 200
    assert health.json()["data"]["risk_level"] in {"High", "Critical", "Moderate", "Low", "Very Low"}

    forecast = client.get(
        "/assets/asset_w12_bridge_0042/forecast",
        headers=AUTH_HEADERS,
        params={"horizon_hours": 48},
    )
    assert forecast.status_code == 200
    assert forecast.json()["data"]["horizon_hours"] == 48

    verification = client.get(
        "/maintenance/mnt_20260214_0012/verification",
        headers=AUTH_HEADERS,
    )
    assert verification.status_code == 200
    assert verification.json()["data"]["verification_status"] == "confirmed"


def test_rate_limit_enforced() -> None:
    client = TestClient(app)

    limiter = get_rate_limiter()
    limiter.set_limits(limit=2, window_seconds=60)

    assert client.get("/assets", headers=AUTH_HEADERS).status_code == 200
    assert client.get("/assets", headers=AUTH_HEADERS).status_code == 200

    third = client.get("/assets", headers=AUTH_HEADERS)
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "RATE_LIMITED"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "infraguard_api_gateway_rate_limited_total 1" in metrics.text
