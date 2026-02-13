"""Contract tests for fuzzy inference request/response/event payloads."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/fuzzy-inference-service/src"))

from fuzzy_inference.events import build_asset_risk_computed_event  # noqa: E402
from fuzzy_inference.main import app  # noqa: E402


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


def test_fuzzy_request_response_event_contracts() -> None:
    request_payload = {
        "asset_id": "asset_w12_bridge_42",
        "inputs": {
            "strain": 0.74,
            "vibration": 0.62,
            "temperature": 0.68,
            "rainfall_intensity": 0.45,
            "traffic_density": 0.81,
            "failure_probability": 0.65,
            "anomaly_score": 0.72,
        },
    }

    request_validator = _validator("contracts/ml/fuzzy.infer.request.schema.json")
    response_validator = _validator("contracts/ml/fuzzy.infer.response.schema.json")
    event_validator = _validator("contracts/events/asset.risk.computed.schema.json")

    request_validator.validate(request_payload)

    client = TestClient(app)
    response = client.post(
        "/infer",
        json=request_payload,
        headers={"x-trace-id": "trace-contract-12345678"},
    )
    assert response.status_code == 200
    response_body = response.json()
    response_validator.validate(response_body)

    evaluated_at = datetime.fromisoformat(response_body["data"]["evaluated_at"])
    event = build_asset_risk_computed_event(
        asset_id=response_body["data"]["asset_id"],
        evaluated_at=evaluated_at,
        health_score=response_body["data"]["final_risk_score"],
        risk_level=response_body["data"]["risk_level"],
        failure_probability_72h=request_payload["inputs"]["failure_probability"],
        anomaly_score=request_payload["inputs"]["anomaly_score"],
        anomaly_threshold=0.7,
        trace_id="trace-contract-12345678",
        produced_by="services/fuzzy-inference-service",
    )
    event_validator.validate(event)
