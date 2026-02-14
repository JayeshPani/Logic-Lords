"""Tests for blockchain verification service."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from blockchain_verification.main import app  # noqa: E402
from blockchain_verification.observability import get_metrics  # noqa: E402
from blockchain_verification.routes import _engine  # noqa: E402
from blockchain_verification.schemas import SepoliaConnectionResponse  # noqa: E402


def _command(
    *,
    maintenance_id: str = "mnt_20260214_0012",
    asset_id: str = "asset_w12_bridge_0042",
) -> dict:
    return {
        "command_id": str(uuid4()),
        "command_type": "verification.record.blockchain",
        "command_version": "v1",
        "requested_at": "2026-02-14T05:00:00+00:00",
        "requested_by": "services/report-generation-service",
        "trace_id": "trace-verification-12345",
        "payload": {
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "evidence_hash": "0x" + "a" * 64,
            "network": "sepolia",
            "contract_address": "0x" + "1" * 40,
            "chain_id": 11155111,
        },
    }


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    _engine.reset_state_for_tests()
    get_metrics().reset()


def test_record_creates_submitted_verification() -> None:
    client = TestClient(app)

    response = client.post("/record", json=_command())
    assert response.status_code == 200
    body = response.json()
    verification = body["verification"]

    assert verification["verification_status"] == "submitted"
    assert verification["confirmations"] == 0
    assert verification["required_confirmations"] == 3
    assert verification["tx_hash"].startswith("0x")
    assert len(verification["tx_hash"]) == 66

    fetch = client.get("/verifications/mnt_20260214_0012")
    assert fetch.status_code == 200
    assert fetch.json()["verification_id"] == verification["verification_id"]


def test_track_progresses_to_confirmed_and_emits_event() -> None:
    client = TestClient(app)
    assert client.post("/record", json=_command()).status_code == 200

    first = client.post("/verifications/mnt_20260214_0012/track")
    assert first.status_code == 200
    assert first.json()["verification"]["verification_status"] == "submitted"
    assert first.json()["verification"]["confirmations"] == 1
    assert first.json().get("maintenance_verified_event") is None

    second = client.post("/verifications/mnt_20260214_0012/track")
    assert second.status_code == 200
    assert second.json()["verification"]["confirmations"] == 2

    third = client.post("/verifications/mnt_20260214_0012/track")
    assert third.status_code == 200
    body = third.json()
    assert body["verification"]["verification_status"] == "confirmed"
    assert body["verification"]["confirmations"] == 3
    assert body["maintenance_verified_event"]["event_type"] == "maintenance.verified.blockchain"


def test_duplicate_record_returns_conflict() -> None:
    client = TestClient(app)

    first = client.post("/record", json=_command())
    assert first.status_code == 200

    duplicate = client.post("/record", json=_command())
    assert duplicate.status_code == 409
    assert "verification already exists" in duplicate.json()["detail"]


def test_list_verifications_with_filters() -> None:
    client = TestClient(app)

    assert client.post("/record", json=_command(maintenance_id="mnt_20260214_0012")).status_code == 200
    assert client.post("/record", json=_command(maintenance_id="mnt_20260214_0013", asset_id="asset_w12_road_0101")).status_code == 200

    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200
    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200
    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200

    all_items = client.get("/verifications")
    assert all_items.status_code == 200
    assert len(all_items.json()["items"]) == 2

    confirmed_items = client.get("/verifications", params={"status": "confirmed"})
    assert confirmed_items.status_code == 200
    assert len(confirmed_items.json()["items"]) == 1

    asset_items = client.get("/verifications", params={"asset_id": "asset_w12_road_0101"})
    assert asset_items.status_code == 200
    assert len(asset_items.json()["items"]) == 1


def test_metrics_track_record_and_confirmation_calls() -> None:
    client = TestClient(app)

    assert client.post("/record", json=_command()).status_code == 200
    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200
    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200
    assert client.post("/verifications/mnt_20260214_0012/track").status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "infraguard_verification_record_requests_total 1" in metrics.text
    assert "infraguard_verification_track_requests_total 3" in metrics.text
    assert "infraguard_verification_submitted_total 1" in metrics.text
    assert "infraguard_verification_confirmed_total 1" in metrics.text


def test_onchain_connect_returns_not_configured_when_rpc_missing() -> None:
    client = TestClient(app)

    response = client.post("/onchain/connect")
    assert response.status_code == 200

    body = response.json()
    assert body["network"] == "sepolia"
    assert body["connected"] is False
    assert body["expected_chain_id"] == 11155111
    assert "SEPOLIA_RPC_URL" in body["message"]


def test_onchain_connect_uses_engine_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    expected = SepoliaConnectionResponse(
        connected=True,
        network="sepolia",
        expected_chain_id=11155111,
        chain_id=11155111,
        latest_block=100001,
        contract_address="0x" + "1" * 40,
        contract_deployed=True,
        checked_at=datetime.now(tz=timezone.utc),
        message="Connected to Sepolia RPC.",
    )

    monkeypatch.setattr(_engine, "connect_sepolia", lambda: expected)

    response = client.post("/onchain/connect")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["chain_id"] == 11155111
    assert body["latest_block"] == 100001
    assert body["contract_deployed"] is True


def test_onchain_connect_ignores_invalid_contract_address_config() -> None:
    client = TestClient(app)

    previous = _engine._settings.sepolia_contract_address
    _engine._settings.sepolia_contract_address = "0x<your-contract-address>"
    try:
        response = client.post("/onchain/connect")
    finally:
        _engine._settings.sepolia_contract_address = previous

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["contract_address"] is None
    assert "ignored" in body["message"].lower()


def test_onchain_connect_returns_structured_failure_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)

    def _raise_unexpected() -> SepoliaConnectionResponse:
        raise RuntimeError("unexpected failure from engine")

    monkeypatch.setattr(_engine, "connect_sepolia", _raise_unexpected)

    response = client.post("/onchain/connect")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["network"] == "sepolia"
    assert "failed" in body["message"].lower()
