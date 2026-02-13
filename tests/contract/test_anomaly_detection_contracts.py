"""Contract tests for anomaly detect request/response/event payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/anomaly-detection-service/src"))

from anomaly_detection.engine import AnomalyDetector  # noqa: E402
from anomaly_detection.config import Settings  # noqa: E402
from anomaly_detection.events import build_asset_anomaly_detected_event  # noqa: E402
from anomaly_detection.main import app  # noqa: E402


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


def _baseline(n: int) -> list[dict]:
    return [
        {
            "strain": 0.2 + (0.01 * (i % 3)),
            "vibration": 0.25 + (0.01 * (i % 2)),
            "temperature": 0.35 + (0.01 * (i % 4)),
            "humidity": 0.45 + (0.01 * (i % 3)),
        }
        for i in range(n)
    ]


def test_anomaly_request_response_event_contracts() -> None:
    request_payload = {
        "asset_id": "asset_w12_bridge_42",
        "current": {"strain": 0.78, "vibration": 0.82, "temperature": 0.64, "humidity": 0.55},
        "baseline_window": _baseline(24),
    }

    request_validator = _validator("contracts/ml/anomaly.detect.request.schema.json")
    response_validator = _validator("contracts/ml/anomaly.detect.response.schema.json")
    event_validator = _validator("contracts/events/asset.anomaly.detected.schema.json")

    request_validator.validate(request_payload)

    client = TestClient(app)
    response = client.post(
        "/detect",
        json=request_payload,
        headers={"x-trace-id": "trace-contract-anomaly-123456"},
    )
    assert response.status_code == 200
    response_body = response.json()
    response_validator.validate(response_body)

    detector = AnomalyDetector(Settings(min_baseline_points=8, anomaly_threshold=0.65))
    result = detector.detect(
        current=request_payload["current"],
        baseline_window=request_payload["baseline_window"],
    )
    event = build_asset_anomaly_detected_event(
        asset_id=response_body["data"]["asset_id"],
        evaluated_at=datetime.fromisoformat(response_body["data"]["evaluated_at"]),
        result=result,
        trace_id="trace-contract-anomaly-123456",
        produced_by="services/anomaly-detection-service",
    )
    event_validator.validate(event)
