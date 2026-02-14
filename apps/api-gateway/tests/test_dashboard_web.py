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
    assert "ops-kpi-grid" in response.text
    assert "triage-list" in response.text
    assert "selected-asset-title" in response.text
    assert "verify-chain-btn" in response.text
    assert "track-verification-btn" in response.text
    assert "risk-map-status" in response.text
    assert "Automation" in response.text
    assert "automation-incident-list" in response.text
    assert "maintenance-evidence-panel" in response.text
    assert "evidence-file-input" in response.text
    assert "evidence-upload-btn" in response.text
    assert "submit-verification-btn" in response.text
    assert "evidence-list-body" in response.text


def test_dashboard_static_assets_served() -> None:
    client = TestClient(app)
    css = client.get("/dashboard-static/styles.css")
    js = client.get("/dashboard-static/main.js")

    assert css.status_code == 200
    assert "--accent-blue" in css.text
    assert js.status_code == 200
    assert "refreshDashboard" in js.text
