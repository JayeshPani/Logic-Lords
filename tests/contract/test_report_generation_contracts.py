"""Contract tests for report generation command and output messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/report-generation-service/src"))

from report_generation.main import app  # noqa: E402
from report_generation.routes import _engine  # noqa: E402


def _absolutize_refs(schema: object, schema_path: Path) -> object:
    if isinstance(schema, dict):
        updated: dict[str, object] = {}
        for key, value in schema.items():
            if key == "$ref" and isinstance(value, str):
                if value.startswith("#") or "://" in value:
                    updated[key] = value
                else:
                    updated[key] = (schema_path.parent / value).resolve().as_uri()
            else:
                updated[key] = _absolutize_refs(value, schema_path)
        return updated

    if isinstance(schema, list):
        return [_absolutize_refs(item, schema_path) for item in schema]

    return schema


def _build_schema_store() -> tuple[dict[str, dict], Registry]:
    store: dict[str, dict] = {}
    for schema_path in (ROOT / "contracts").rglob("*.json"):
        schema = _absolutize_refs(json.loads(schema_path.read_text()), schema_path.resolve())
        if not isinstance(schema, dict):
            continue
        uri = schema_path.resolve().as_uri()
        store[uri] = schema
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            store[schema_id] = schema

    registry = Registry()
    for uri, schema in store.items():
        if "://" not in uri:
            continue
        registry = registry.with_resource(uri, Resource.from_contents(schema))
    return store, registry


def _validator(schema_rel_path: str) -> jsonschema.Draft202012Validator:
    store, registry = _build_schema_store()
    schema_uri = (ROOT / schema_rel_path).resolve().as_uri()
    schema = store[schema_uri]
    return jsonschema.Draft202012Validator(
        schema=schema,
        registry=registry,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )


def test_report_generation_contracts() -> None:
    _engine.reset_state_for_tests()

    now = datetime.now(tz=timezone.utc)
    earlier = now - timedelta(hours=2)

    inspection_event = {
        "event_id": str(uuid4()),
        "event_type": "inspection.requested",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "apps/orchestration-service",
        "trace_id": "trace-contract-report-inspection-001",
        "data": {
            "ticket_id": "insp_20260214_0008",
            "asset_id": "asset_w12_bridge_0042",
            "requested_at": now.isoformat(),
            "priority": "high",
            "reason": "high risk and anomaly flag",
        },
    }

    maintenance_event = {
        "event_id": str(uuid4()),
        "event_type": "maintenance.completed",
        "event_version": "v1",
        "occurred_at": now.isoformat(),
        "produced_by": "apps/orchestration-service",
        "trace_id": "trace-contract-report-maintenance-001",
        "data": {
            "maintenance_id": "mnt_20260214_0008",
            "asset_id": "asset_w12_bridge_0042",
            "completed_at": now.isoformat(),
            "performed_by": "team-alpha",
            "summary": "critical weld repair and load retest completed",
        },
    }

    command = {
        "command_id": str(uuid4()),
        "command_type": "report.generate",
        "command_version": "v1",
        "requested_at": now.isoformat(),
        "requested_by": "services/report-generation-service",
        "trace_id": "trace-contract-report-command-001",
        "payload": {
            "maintenance_id": "mnt_20260214_0008",
            "asset_id": "asset_w12_bridge_0042",
            "report_type": "maintenance_verification",
            "include_sensor_window": {
                "from": earlier.isoformat(),
                "to": now.isoformat(),
            },
        },
    }

    inspection_validator = _validator("contracts/events/inspection.requested.schema.json")
    maintenance_validator = _validator("contracts/events/maintenance.completed.schema.json")
    report_command_validator = _validator("contracts/commands/report.generate.command.schema.json")
    report_generated_validator = _validator("contracts/events/report.generated.schema.json")
    verification_command_validator = _validator(
        "contracts/commands/verification.record.blockchain.command.schema.json"
    )

    inspection_validator.validate(inspection_event)
    maintenance_validator.validate(maintenance_event)
    report_command_validator.validate(command)

    client = TestClient(app)

    assert client.post("/events/inspection-requested", json=inspection_event).status_code == 200
    assert client.post("/events/maintenance-completed", json=maintenance_event).status_code == 200

    response = client.post(
        "/generate",
        json={
            "command": command,
            "generated_at": now.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()

    report_generated_validator.validate(body["report_generated_event"])
    verification_command_validator.validate(body["verification_record_command"])
