"""Tests for Firebase-backed sensor ingestion service."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

import main as sensor_main  # noqa: E402


@pytest.fixture(autouse=True)
def configure_settings() -> None:
    sensor_main.settings.firebase_db_url = "https://example-default-rtdb.firebaseio.com"
    sensor_main.settings.firebase_auth_token = None
    sensor_main.settings.firebase_path_prefix = "infraguard"
    sensor_main.settings.telemetry_window_size = 8


def test_latest_telemetry_computes_expected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(sensor_main.app)

    latest = {
        "device_id": "esp32-node-01",
        "captured_at": "2026-02-14T12:00:00+00:00",
        "firmware_version": "1.0.0",
        "dht11": {"temperature_c": 28.6, "humidity_pct": 62.0},
        "accelerometer": {"x_g": 0.02, "y_g": -0.03, "z_g": 0.99},
    }
    history = {
        "-a": {
            "device_id": "esp32-node-01",
            "captured_at": "2026-02-14T11:59:00+00:00",
            "firmware_version": "1.0.0",
            "dht11": {"temperature_c": 28.1, "humidity_pct": 61.4},
            "accelerometer": {"x_g": 0.01, "y_g": -0.02, "z_g": 0.98},
        },
        "-b": latest,
    }

    def fake_firebase_request(method: str, path: str, payload=None, query=None):  # noqa: ANN001
        assert method == "GET"
        if path.endswith("/latest"):
            return latest
        if path.endswith("/history"):
            return history
        return {}

    monkeypatch.setattr(sensor_main, "_firebase_request", fake_firebase_request)

    response = client.get("/telemetry/assets/asset_w12_bridge_0042/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "asset_w12_bridge_0042"
    assert body["source"] == "firebase"
    assert set(body["sensors"].keys()) >= {"strain", "vibration", "temperature", "tilt", "humidity"}
    assert 0 <= body["computed"]["health_proxy_score"] <= 1


def test_ingest_writes_latest_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(sensor_main.app)
    writes: list[tuple[str, str]] = []

    def fake_firebase_request(method: str, path: str, payload=None, query=None):  # noqa: ANN001
        writes.append((method, path))
        return {"name": "-Npush"} if method == "POST" else {}

    monkeypatch.setattr(sensor_main, "_firebase_request", fake_firebase_request)

    payload = {
        "device_id": "esp32-node-01",
        "captured_at": "2026-02-14T12:02:00+00:00",
        "firmware_version": "1.0.0",
        "dht11": {"temperature_c": 28.7, "humidity_pct": 62.2},
        "accelerometer": {"x_g": 0.01, "y_g": -0.01, "z_g": 1.0},
    }

    response = client.post("/telemetry/assets/asset_w12_bridge_0042/ingest", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "asset_w12_bridge_0042"
    assert ("PUT", "infraguard/telemetry/asset_w12_bridge_0042/latest") in writes
    assert ("POST", "infraguard/telemetry/asset_w12_bridge_0042/history") in writes
