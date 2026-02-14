"""Smoke tests for dashboard-web integration in API gateway."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from api_gateway.main import app  # noqa: E402


def test_dashboard_page_served() -> None:
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "InfraGuard Control Room" in response.text
    assert "Connect Wallet" in response.text


def test_dashboard_static_assets_served() -> None:
    client = TestClient(app)
    css = client.get("/dashboard-static/styles.css")
    js = client.get("/dashboard-static/main.js")

    assert css.status_code == 200
    assert "--accent-blue" in css.text
    assert js.status_code == 200
    assert "refreshDashboard" in js.text
