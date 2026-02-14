"""Contract tests for orchestration request/response/event payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "apps/orchestration-service/src"))

from orchestration_service.main import app  # noqa: E402
from orchestration_service.routes import _engine  # noqa: E402


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


def test_orchestration_event_and_command_contracts() -> None:
    _engine.reset_state_for_tests()

    now = datetime.now(tz=timezone.utc).isoformat()
    forecast_payload = {
        "event_id": str(uuid4()),
        "event_type": "asset.failure.predicted",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "services/lstm-forecast-service",
        "trace_id": "trace-contract-orch-forecast-001",
        "data": {
            "asset_id": "asset_w12_bridge_0042",
            "generated_at": now,
            "horizon_hours": 72,
            "failure_probability_72h": 0.86,
            "confidence": 0.79,
        },
    }

    risk_payload = {
        "event_id": str(uuid4()),
        "event_type": "asset.risk.computed",
        "event_version": "v1",
        "occurred_at": now,
        "produced_by": "services/health-score-service",
        "trace_id": "trace-contract-orch-risk-001",
        "data": {
            "asset_id": "asset_w12_bridge_0042",
            "evaluated_at": now,
            "health_score": 0.76,
            "risk_level": "High",
            "failure_probability_72h": 0.64,
            "anomaly_flag": 1,
        },
    }

    forecast_validator = _validator("contracts/events/asset.failure.predicted.schema.json")
    risk_validator = _validator("contracts/events/asset.risk.computed.schema.json")
    inspection_event_validator = _validator("contracts/events/inspection.requested.schema.json")
    maintenance_event_validator = _validator("contracts/events/maintenance.completed.schema.json")
    inspection_command_validator = _validator("contracts/commands/inspection.create.command.schema.json")

    forecast_validator.validate(forecast_payload)
    risk_validator.validate(risk_payload)

    client = TestClient(app)

    forecast_response = client.post("/events/asset-failure-predicted", json=forecast_payload)
    assert forecast_response.status_code == 200

    risk_response = client.post("/events/asset-risk-computed", json=risk_payload)
    assert risk_response.status_code == 200

    body = risk_response.json()
    assert body["workflow_triggered"] is True
    assert body["workflow_id"]

    inspection_command_validator.validate(body["inspection_create_command"])
    inspection_event_validator.validate(body["inspection_requested_event"])

    maintenance_response = client.post(
        f"/workflows/{body['workflow_id']}/maintenance/completed",
        json={"performed_by": "team-alpha", "summary": "critical bearing replaced"},
    )
    assert maintenance_response.status_code == 200
    maintenance_body = maintenance_response.json()
    maintenance_event_validator.validate(maintenance_body["maintenance_completed_event"])
