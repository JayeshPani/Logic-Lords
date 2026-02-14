"""Tests for report generation service."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from report_generation.main import app
from report_generation.observability import get_metrics
from report_generation import routes as report_routes
from report_generation.routes import _engine
from report_generation.storage_adapter import StoredObjectInfo, UploadSession


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


@dataclass
class FakeStorageAdapter:
    """In-memory fake for Firebase storage adapter behavior."""

    expected_content_type: str = "application/pdf"
    expected_size_bytes: int = 20480
    sha256_hex: str = "a" * 64

    def create_upload_session(self, *, object_path: str, content_type: str) -> UploadSession:
        assert content_type == self.expected_content_type
        expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=15)
        return UploadSession(
            upload_url=f"https://upload.test.local/{object_path}",
            upload_method="PUT",
            upload_headers={"Content-Type": content_type},
            expires_at=expires_at,
            storage_uri=f"gs://bucket/{object_path}",
            object_path=object_path,
        )

    def get_object_info(self, *, object_path: str) -> StoredObjectInfo:
        assert object_path
        return StoredObjectInfo(size_bytes=self.expected_size_bytes, content_type=self.expected_content_type)

    def compute_sha256(self, *, object_path: str) -> str:
        assert object_path
        return self.sha256_hex


@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _engine.reset_state_for_tests()
    get_metrics().reset()
    monkeypatch.setattr(report_routes, "_storage_adapter", FakeStorageAdapter())


def _upload_and_finalize_evidence(client: TestClient, maintenance_id: str, asset_id: str) -> dict:
    upload = client.post(
        f"/maintenance/{maintenance_id}/evidence/uploads",
        json={
            "asset_id": asset_id,
            "filename": "repair_report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 20480,
            "uploaded_by": "org-admin-01",
            "category": "inspection_report",
            "notes": "Bridge deck crack repair report",
        },
    )
    assert upload.status_code == 200
    evidence_id = upload.json()["evidence"]["evidence_id"]

    finalize = client.post(
        f"/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize",
        json={"uploaded_by": "org-admin-01"},
    )
    assert finalize.status_code == 200
    return finalize.json()["evidence"]


def test_generate_report_returns_bundle_and_messages() -> None:
    client = TestClient(app)

    maintenance = _maintenance_event()
    maintenance_id = maintenance["data"]["maintenance_id"]
    asset_id = maintenance["data"]["asset_id"]

    assert client.post("/events/inspection-requested", json=_inspection_event()).status_code == 200
    assert client.post("/events/maintenance-completed", json=maintenance).status_code == 200

    evidence = _upload_and_finalize_evidence(client, maintenance_id, asset_id)
    assert evidence["status"] == "finalized"
    assert evidence["sha256_hex"] == "a" * 64

    response = client.post("/generate", json=_generate_command())
    assert response.status_code == 200
    body = response.json()

    assert body["report_bundle"]["report_id"].startswith("rpt_")
    assert body["report_bundle"]["evidence_hash"].startswith("0x")
    assert len(body["report_bundle"]["evidence_hash"]) == 66

    assert body["report_generated_event"]["event_type"] == "report.generated"
    assert body["verification_record_command"]["command_type"] == "verification.record.blockchain"
    assert body["report_bundle"]["sections"]["uploaded_evidence_count"] == 1


def test_generate_requires_maintenance_context() -> None:
    client = TestClient(app)

    response = client.post("/generate", json=_generate_command())
    assert response.status_code == 404
    assert "maintenance context not found" in response.json()["detail"]


def test_generate_requires_finalized_evidence() -> None:
    client = TestClient(app)
    assert client.post("/events/inspection-requested", json=_inspection_event()).status_code == 200
    assert client.post("/events/maintenance-completed", json=_maintenance_event()).status_code == 200

    response = client.post("/generate", json=_generate_command())
    assert response.status_code == 409
    assert "EVIDENCE_REQUIRED" in response.json()["detail"]


def test_evidence_create_finalize_and_list() -> None:
    client = TestClient(app)
    maintenance = _maintenance_event()
    maintenance_id = maintenance["data"]["maintenance_id"]
    asset_id = maintenance["data"]["asset_id"]

    assert client.post("/events/maintenance-completed", json=maintenance).status_code == 200

    finalized = _upload_and_finalize_evidence(client, maintenance_id, asset_id)
    assert finalized["status"] == "finalized"

    listed = client.get(f"/maintenance/{maintenance_id}/evidence")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "finalized"


def test_metrics_track_context_and_generation() -> None:
    client = TestClient(app)

    before = client.get("/metrics")
    assert before.status_code == 200
    assert "infraguard_report_generation_requests_total 0" in before.text

    maintenance = _maintenance_event()
    maintenance_id = maintenance["data"]["maintenance_id"]
    asset_id = maintenance["data"]["asset_id"]
    assert client.post("/events/inspection-requested", json=_inspection_event()).status_code == 200
    assert client.post("/events/maintenance-completed", json=maintenance).status_code == 200
    _upload_and_finalize_evidence(client, maintenance_id, asset_id)
    assert client.post("/generate", json=_generate_command()).status_code == 200

    after = client.get("/metrics")
    assert after.status_code == 200
    assert "infraguard_report_generation_requests_total 1" in after.text
    assert "infraguard_report_generation_success_total 1" in after.text
    assert "infraguard_report_generation_errors_total 0" in after.text
    assert "infraguard_report_generation_inspection_context_events_total 1" in after.text
    assert "infraguard_report_generation_maintenance_context_events_total 1" in after.text
