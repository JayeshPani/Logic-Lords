"""Contract tests for health score request/response/event payloads."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/health-score-service/src"))

from health_score.events import build_asset_risk_computed_event  # noqa: E402
from health_score.main import app  # noqa: E402


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


def test_health_score_request_response_event_contracts() -> None:
    request_payload = {
        "asset_id": "asset_w12_bridge_42",
        "final_risk_score": 0.73,
        "failure_probability_72h": 0.65,
        "anomaly_flag": 0,
    }

    request_validator = _validator("contracts/ml/health.score.request.schema.json")
    response_validator = _validator("contracts/ml/health.score.response.schema.json")
    event_validator = _validator("contracts/events/asset.risk.computed.schema.json")

    request_validator.validate(request_payload)

    client = TestClient(app)
    response = client.post(
        "/compose",
        json=request_payload,
        headers={"x-trace-id": "trace-contract-health-123456"},
    )
    assert response.status_code == 200
    response_body = response.json()
    response_validator.validate(response_body)

    evaluated_at = datetime.fromisoformat(response_body["timestamp"])
    event = build_asset_risk_computed_event(
        asset_id=request_payload["asset_id"],
        evaluated_at=evaluated_at,
        health_score=response_body["health_score"],
        risk_level=response_body["risk_level"],
        failure_probability_72h=response_body["failure_probability_72h"],
        anomaly_flag=response_body["anomaly_flag"],
        trace_id="trace-contract-health-123456",
        produced_by="services/health-score-service",
    )
    event_validator.validate(event)
