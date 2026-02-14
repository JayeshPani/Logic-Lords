"""Tests for API gateway."""

import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from api_gateway.main import app  # noqa: E402
from api_gateway.observability import get_metrics  # noqa: E402
from api_gateway.errors import ApiError  # noqa: E402
from api_gateway import routes as gateway_routes  # noqa: E402
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


def test_health_forecast_and_verification_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
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

    def fake_verification_request(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id, body
        assert method == "GET"
        assert path == "/verifications/mnt_20260214_0012"
        return {
            "verification_id": "vfy_20260214_0001",
            "command_id": str(uuid4()),
            "maintenance_id": "mnt_20260214_0012",
            "asset_id": "asset_w12_bridge_0042",
            "verification_status": "confirmed",
            "evidence_hash": "0x" + "a" * 64,
            "tx_hash": "0x" + "b" * 64,
            "network": "sepolia",
            "contract_address": "0x" + "1" * 40,
            "chain_id": 11155111,
            "block_number": 123456,
            "confirmations": 3,
            "required_confirmations": 3,
            "submitted_at": "2026-02-14T12:00:00+00:00",
            "confirmed_at": "2026-02-14T12:02:00+00:00",
            "created_at": "2026-02-14T12:00:00+00:00",
            "updated_at": "2026-02-14T12:02:00+00:00",
            "trace_id": "trace-verification-12345",
        }

    monkeypatch.setattr(gateway_routes, "_request_blockchain_verification", fake_verification_request)

    verification = client.get(
        "/maintenance/mnt_20260214_0012/verification",
        headers=AUTH_HEADERS,
    )
    assert verification.status_code == 200
    assert verification.json()["data"]["verification_status"] == "confirmed"
    assert verification.json()["data"]["confirmations"] == 3


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


def test_blockchain_connect_proxies_sepolia_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_connect(_trace_id: str) -> dict:
        return {
            "connected": True,
            "network": "sepolia",
            "expected_chain_id": 11155111,
            "chain_id": 11155111,
            "latest_block": 100042,
            "contract_address": "0x" + "1" * 40,
            "contract_deployed": True,
            "checked_at": "2026-02-14T06:00:00+00:00",
            "message": "Connected to Sepolia RPC.",
        }

    monkeypatch.setattr(gateway_routes, "_connect_blockchain_service", fake_connect)

    response = client.post("/blockchain/connect", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["network"] == "sepolia"
    assert body["chain_id"] == 11155111
    assert body["contract_deployed"] is True


def test_blockchain_connect_returns_error_when_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_connect(_trace_id: str) -> dict:
        raise ApiError(
            status_code=503,
            code="BLOCKCHAIN_UNAVAILABLE",
            message="Blockchain service unreachable: connection refused",
            trace_id="trc_test_gateway_001",
        )

    monkeypatch.setattr(gateway_routes, "_connect_blockchain_service", fake_connect)

    response = client.post("/blockchain/connect", headers=AUTH_HEADERS)
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "BLOCKCHAIN_UNAVAILABLE"


def test_blockchain_connect_maps_timeout_to_504(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_connect(_trace_id: str) -> dict:
        raise ApiError(
            status_code=504,
            code="BLOCKCHAIN_TIMEOUT",
            message="Blockchain service timed out after 15.0s.",
            trace_id="trc_test_gateway_001",
        )

    monkeypatch.setattr(gateway_routes, "_connect_blockchain_service", fake_connect)

    response = client.post("/blockchain/connect", headers=AUTH_HEADERS)
    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "BLOCKCHAIN_TIMEOUT"


def test_connect_blockchain_service_timeout_raises_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(gateway_routes.url_request, "urlopen", fake_urlopen)

    previous_timeout = gateway_routes._settings.blockchain_connect_timeout_seconds
    gateway_routes._settings.blockchain_connect_timeout_seconds = 1.5
    try:
        with pytest.raises(ApiError) as exc_info:
            gateway_routes._connect_blockchain_service("trc_test_gateway_001")
    finally:
        gateway_routes._settings.blockchain_connect_timeout_seconds = previous_timeout

    assert exc_info.value.status_code == 504
    assert exc_info.value.code == "BLOCKCHAIN_TIMEOUT"


def test_connect_blockchain_service_uses_fallback_url(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "connected": True,
        "network": "sepolia",
        "expected_chain_id": 11155111,
        "chain_id": 11155111,
        "latest_block": 100042,
        "contract_address": None,
        "contract_deployed": None,
        "checked_at": "2026-02-14T06:00:00+00:00",
        "message": "Connected to Sepolia RPC.",
    }

    class FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._body.encode("utf-8")

    def fake_urlopen(request: object, timeout: float):  # noqa: ARG001
        url = getattr(request, "full_url")
        if url.startswith("http://127.0.0.1:8105"):
            raise gateway_routes.url_error.URLError("[Errno 61] Connection refused")
        return FakeResponse(json.dumps(payload))

    monkeypatch.setattr(gateway_routes.url_request, "urlopen", fake_urlopen)

    previous_base = gateway_routes._settings.blockchain_verification_base_url
    previous_fallbacks = gateway_routes._settings.blockchain_verification_fallback_urls_csv
    gateway_routes._settings.blockchain_verification_base_url = "http://127.0.0.1:8105"
    gateway_routes._settings.blockchain_verification_fallback_urls_csv = "http://127.0.0.1:8235"
    try:
        result = gateway_routes._connect_blockchain_service("trc_test_gateway_001")
    finally:
        gateway_routes._settings.blockchain_verification_base_url = previous_base
        gateway_routes._settings.blockchain_verification_fallback_urls_csv = previous_fallbacks

    assert result["connected"] is True
    assert result["chain_id"] == 11155111


def test_connect_blockchain_service_unavailable_includes_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float):  # noqa: ARG001
        url = getattr(request, "full_url")
        raise gateway_routes.url_error.URLError(f"refused for {url}")

    monkeypatch.setattr(gateway_routes.url_request, "urlopen", fake_urlopen)

    previous_base = gateway_routes._settings.blockchain_verification_base_url
    previous_fallbacks = gateway_routes._settings.blockchain_verification_fallback_urls_csv
    gateway_routes._settings.blockchain_verification_base_url = "http://127.0.0.1:8105"
    gateway_routes._settings.blockchain_verification_fallback_urls_csv = "http://127.0.0.1:8235"
    try:
        with pytest.raises(ApiError) as exc_info:
            gateway_routes._connect_blockchain_service("trc_test_gateway_001")
    finally:
        gateway_routes._settings.blockchain_verification_base_url = previous_base
        gateway_routes._settings.blockchain_verification_fallback_urls_csv = previous_fallbacks

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "BLOCKCHAIN_UNAVAILABLE"
    assert "Tried:" in exc_info.value.message


def test_asset_telemetry_proxies_sensor_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_fetch(asset_id: str, _trace_id: str) -> dict:
        assert asset_id == "asset_w12_bridge_0042"
        return {
            "asset_id": asset_id,
            "source": "firebase",
            "captured_at": "2026-02-14T12:00:00+00:00",
            "sensors": {
                "strain": {
                    "value": 13.5,
                    "unit": "me",
                    "delta": "+0.2 variance",
                    "samples": [12.8, 13.1, 13.3, 13.5],
                },
                "vibration": {
                    "value": 1.2,
                    "unit": "mm/s",
                    "delta": "+0.1 trend",
                    "samples": [0.9, 1.0, 1.1, 1.2],
                },
                "temperature": {
                    "value": 29.2,
                    "unit": "C",
                    "delta": "+0.4 spike",
                    "samples": [28.1, 28.5, 28.8, 29.2],
                },
                "tilt": {
                    "value": 3.5,
                    "unit": "deg",
                    "delta": "+0.2 drift",
                    "samples": [2.9, 3.1, 3.2, 3.5],
                },
            },
            "computed": {
                "acceleration_magnitude_g": 1.01,
                "vibration_rms_ms2": 1.2,
                "tilt_deg": 3.5,
                "strain_proxy_microstrain": 13.5,
                "thermal_stress_index": 0.38,
                "fatigue_index": 0.19,
                "health_proxy_score": 0.77,
            },
        }

    monkeypatch.setattr(gateway_routes, "_fetch_sensor_telemetry", fake_fetch)

    response = client.get("/telemetry/asset_w12_bridge_0042/latest", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["source"] == "firebase"
    assert body["data"]["sensors"]["temperature"]["value"] == 29.2
    assert body["data"]["computed"]["health_proxy_score"] == 0.77


def test_asset_telemetry_maps_unavailable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_fetch(_asset_id: str, _trace_id: str) -> dict:
        raise ApiError(
            status_code=503,
            code="SENSOR_INGESTION_UNAVAILABLE",
            message="Sensor ingestion service unreachable",
            trace_id="trc_test_gateway_001",
        )

    monkeypatch.setattr(gateway_routes, "_fetch_sensor_telemetry", fake_fetch)

    response = client.get("/telemetry/asset_w12_bridge_0042/latest", headers=AUTH_HEADERS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SENSOR_INGESTION_UNAVAILABLE"


def test_track_maintenance_verification_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_verification_request(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id, body
        assert method == "POST"
        assert path == "/verifications/mnt_20260214_0012/track"
        return {
            "verification": {
                "verification_id": "vfy_20260214_0001",
                "command_id": str(uuid4()),
                "maintenance_id": "mnt_20260214_0012",
                "asset_id": "asset_w12_bridge_0042",
                "verification_status": "confirmed",
                "evidence_hash": "0x" + "a" * 64,
                "tx_hash": "0x" + "b" * 64,
                "network": "sepolia",
                "contract_address": "0x" + "1" * 40,
                "chain_id": 11155111,
                "block_number": 123456,
                "confirmations": 3,
                "required_confirmations": 3,
                "submitted_at": "2026-02-14T12:00:00+00:00",
                "confirmed_at": "2026-02-14T12:03:00+00:00",
                "created_at": "2026-02-14T12:00:00+00:00",
                "updated_at": "2026-02-14T12:03:00+00:00",
                "trace_id": "trace-verification-12345",
            },
            "maintenance_verified_event": {
                "event_type": "maintenance.verified.blockchain",
            },
        }

    monkeypatch.setattr(gateway_routes, "_request_blockchain_verification", fake_verification_request)

    response = client.post(
        "/maintenance/mnt_20260214_0012/verification/track",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["verification_status"] == "confirmed"
    assert body["data"]["confirmations"] == 3
    assert body["maintenance_verified_event"]["event_type"] == "maintenance.verified.blockchain"


def test_automation_incidents_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_request_orchestration(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id, body
        assert method == "GET"
        assert path == "/incidents"
        return {
            "items": [
                {
                    "workflow_id": "wf_20260214_120001_0001",
                    "asset_id": "asset_w12_bridge_0042",
                    "risk_priority": "critical",
                    "escalation_stage": "management_notified",
                    "status": "inspection_requested",
                    "trigger_reason": "risk_level=Critical",
                    "created_at": "2026-02-14T12:00:01+00:00",
                    "updated_at": "2026-02-14T12:00:01+00:00",
                    "authority_notified_at": "2026-02-14T12:00:01+00:00",
                    "authority_ack_deadline_at": "2026-02-14T12:30:01+00:00",
                    "management_dispatch_ids": ["dsp_20260214_0001"],
                    "police_dispatch_ids": [],
                }
            ]
        }

    monkeypatch.setattr(gateway_routes, "_request_orchestration", fake_request_orchestration)

    response = client.get("/automation/incidents", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["escalation_stage"] == "management_notified"


def test_automation_acknowledgement_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_request_orchestration(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id
        assert method == "POST"
        assert path == "/incidents/wf_20260214_120001_0001/acknowledge"
        assert body == {"acknowledged_by": "ops-chief-01", "ack_notes": "Maintenance team dispatched"}
        return {
            "workflow_id": "wf_20260214_120001_0001",
            "escalation_stage": "acknowledged",
            "acknowledged_at": "2026-02-14T12:10:01+00:00",
            "acknowledged_by": "ops-chief-01",
            "ack_notes": "Maintenance team dispatched",
            "police_notified_at": None,
        }

    monkeypatch.setattr(gateway_routes, "_request_orchestration", fake_request_orchestration)

    response = client.post(
        "/automation/incidents/wf_20260214_120001_0001/acknowledge",
        headers=AUTH_HEADERS,
        json={"acknowledged_by": "ops-chief-01", "ack_notes": "Maintenance team dispatched"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["workflow_id"] == "wf_20260214_120001_0001"
    assert body["data"]["escalation_stage"] == "acknowledged"


def test_create_evidence_upload_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_report_generation(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id
        assert method == "POST"
        assert path == "/maintenance/mnt_20260214_0012/evidence/uploads"
        assert body is not None
        return {
            "evidence": {
                "evidence_id": "evd_20260215_0001",
                "maintenance_id": "mnt_20260214_0012",
                "asset_id": "asset_w12_bridge_0042",
                "filename": "repair_report.pdf",
                "content_type": "application/pdf",
                "size_bytes": 20480,
                "storage_uri": "gs://bucket/infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                "storage_object_path": "infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                "sha256_hex": None,
                "uploaded_by": "gateway-client",
                "uploaded_at": "2026-02-15T05:00:00+00:00",
                "finalized_at": None,
                "status": "upload_pending",
                "category": "inspection_report",
                "notes": "Bridge deck crack repair report",
            },
            "upload_url": "https://upload.example.dev/signed",
            "upload_method": "PUT",
            "upload_headers": {"Content-Type": "application/pdf"},
            "expires_at": "2026-02-15T05:15:00+00:00",
        }

    monkeypatch.setattr(gateway_routes, "_request_report_generation", fake_report_generation)

    response = client.post(
        "/maintenance/mnt_20260214_0012/evidence/uploads",
        headers=AUTH_HEADERS,
        json={
            "asset_id": "asset_w12_bridge_0042",
            "filename": "repair_report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 20480,
            "category": "inspection_report",
            "notes": "Bridge deck crack repair report",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["evidence_id"] == "evd_20260215_0001"
    assert body["upload_method"] == "PUT"
    assert body["upload_headers"]["Content-Type"] == "application/pdf"


def test_finalize_evidence_upload_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_report_generation(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id
        assert method == "POST"
        assert path == "/maintenance/mnt_20260214_0012/evidence/evd_20260215_0001/finalize"
        assert body == {"uploaded_by": "org-admin-01"}
        return {
            "evidence": {
                "evidence_id": "evd_20260215_0001",
                "maintenance_id": "mnt_20260214_0012",
                "asset_id": "asset_w12_bridge_0042",
                "filename": "repair_report.pdf",
                "content_type": "application/pdf",
                "size_bytes": 20480,
                "storage_uri": "gs://bucket/infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                "storage_object_path": "infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                "sha256_hex": "a" * 64,
                "uploaded_by": "org-admin-01",
                "uploaded_at": "2026-02-15T05:00:00+00:00",
                "finalized_at": "2026-02-15T05:02:00+00:00",
                "status": "finalized",
                "category": "inspection_report",
                "notes": "Bridge deck crack repair report",
            }
        }

    monkeypatch.setattr(gateway_routes, "_request_report_generation", fake_report_generation)

    response = client.post(
        "/maintenance/mnt_20260214_0012/evidence/evd_20260215_0001/finalize",
        headers=AUTH_HEADERS,
        json={"uploaded_by": "org-admin-01"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "finalized"


def test_list_evidence_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_report_generation(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id, body
        assert method == "GET"
        assert path == "/maintenance/mnt_20260214_0012/evidence"
        return {
            "items": [
                {
                    "evidence_id": "evd_20260215_0001",
                    "maintenance_id": "mnt_20260214_0012",
                    "asset_id": "asset_w12_bridge_0042",
                    "filename": "repair_report.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 20480,
                    "storage_uri": "gs://bucket/infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                    "storage_object_path": "infraguard/evidence/mnt_20260214_0012/evd_20260215_0001/repair_report.pdf",
                    "sha256_hex": "a" * 64,
                    "uploaded_by": "org-admin-01",
                    "uploaded_at": "2026-02-15T05:00:00+00:00",
                    "finalized_at": "2026-02-15T05:02:00+00:00",
                    "status": "finalized",
                    "category": "inspection_report",
                    "notes": "Bridge deck crack repair report",
                }
            ]
        }

    monkeypatch.setattr(gateway_routes, "_request_report_generation", fake_report_generation)

    response = client.get(
        "/maintenance/mnt_20260214_0012/evidence",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_submit_verification_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def fake_request_orchestration(*, trace_id: str, method: str, path: str, body: dict | None = None) -> dict:
        del trace_id
        assert method == "POST"
        assert path == "/maintenance/mnt_20260214_0012/verification/submit"
        assert body is not None
        return {
            "workflow_id": "wf_20260214_120001_0001",
            "maintenance_id": "mnt_20260214_0012",
            "verification_status": "submitted",
            "verification_maintenance_id": "mnt_20260214_0012",
            "verification_tx_hash": "0x" + "b" * 64,
            "verification_error": None,
            "verification_updated_at": "2026-02-15T05:10:00+00:00",
        }

    monkeypatch.setattr(gateway_routes, "_request_orchestration", fake_request_orchestration)

    response = client.post(
        "/maintenance/mnt_20260214_0012/verification/submit",
        headers=AUTH_HEADERS,
        json={},
    )
    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "submitted"


def test_evidence_routes_require_organization_role(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    monkeypatch.setenv("API_GATEWAY_AUTH_BEARER_TOKENS_CSV", "dev-token,operator-token")
    monkeypatch.setenv(
        "API_GATEWAY_AUTH_TOKEN_ROLES_CSV",
        "dev-token:organization|operator,operator-token:operator",
    )
    headers = {"Authorization": "Bearer operator-token", "x-trace-id": "trc_test_gateway_001"}

    response = client.get("/maintenance/mnt_20260214_0012/evidence", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
