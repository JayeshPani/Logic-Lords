"""Contract tests for forecast request/response/event payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))

from lstm_forecast.events import build_asset_failure_predicted_event  # noqa: E402
from lstm_forecast.main import app  # noqa: E402
from lstm_forecast.predictor import PredictorResult  # noqa: E402


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


def _history(points: int = 20) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    records: list[dict] = []
    for index in range(points):
        records.append(
            {
                "timestamp": (now - timedelta(minutes=(points - index) * 10)).isoformat(),
                "strain_value": 200 + (index * 35),
                "vibration_rms": 0.8 + (index * 0.12),
                "temperature": 24 + (index * 0.7),
                "humidity": 52 + (index * 0.9),
                "traffic_density": 0.6,
                "rainfall_intensity": 0.3,
            }
        )
    return records


def test_forecast_request_response_event_contracts() -> None:
    request_payload = {
        "asset_id": "asset_w12_bridge_42",
        "horizon_hours": 72,
        "history": _history(),
    }

    request_validator = _validator("contracts/ml/forecast.request.schema.json")
    response_validator = _validator("contracts/ml/forecast.response.schema.json")
    event_validator = _validator("contracts/events/asset.failure.predicted.schema.json")

    request_validator.validate(request_payload)

    client = TestClient(app)
    response = client.post(
        "/forecast",
        json=request_payload,
        headers={"x-trace-id": "trace-contract-forecast-123456"},
    )
    assert response.status_code == 200
    response_body = response.json()
    response_validator.validate(response_body)

    model = response_body["data"]["model"]
    result = PredictorResult(
        failure_probability=response_body["data"]["failure_probability_72h"],
        confidence=response_body["data"]["confidence"],
        model_name=model["name"],
        model_version=model["version"],
        model_mode=model["mode"],
        architecture=model["architecture"],
    )
    generated_at = datetime.fromisoformat(response_body["data"]["generated_at"])
    event = build_asset_failure_predicted_event(
        asset_id=response_body["data"]["asset_id"],
        generated_at=generated_at,
        horizon_hours=response_body["data"]["horizon_hours"],
        result=result,
        trace_id="trace-contract-forecast-123456",
        produced_by="services/lstm-forecast-service",
    )
    event_validator.validate(event)
