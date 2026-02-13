"""Contract tests for blockchain verification command and verified event payloads."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/blockchain-verification-service/src"))

from blockchain_verification.main import app  # noqa: E402
from blockchain_verification.routes import _engine  # noqa: E402


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


def test_blockchain_verification_contracts() -> None:
    _engine.reset_state_for_tests()

    command = {
        "command_id": str(uuid4()),
        "command_type": "verification.record.blockchain",
        "command_version": "v1",
        "requested_at": "2026-02-14T05:00:00+00:00",
        "requested_by": "services/report-generation-service",
        "trace_id": "trace-contract-verification-001",
        "payload": {
            "maintenance_id": "mnt_20260214_0015",
            "asset_id": "asset_w12_bridge_0042",
            "evidence_hash": "0x" + "a" * 64,
            "network": "sepolia",
            "contract_address": "0x" + "1" * 40,
            "chain_id": 11155111,
        },
    }

    command_validator = _validator("contracts/commands/verification.record.blockchain.command.schema.json")
    event_validator = _validator("contracts/events/maintenance.verified.blockchain.schema.json")

    command_validator.validate(command)

    client = TestClient(app)
    record_response = client.post("/record", json=command)
    assert record_response.status_code == 200

    # required_confirmations is 3 by default
    assert client.post("/verifications/mnt_20260214_0015/track").status_code == 200
    assert client.post("/verifications/mnt_20260214_0015/track").status_code == 200
    track_response = client.post("/verifications/mnt_20260214_0015/track")
    assert track_response.status_code == 200

    body = track_response.json()
    assert body["verification"]["verification_status"] == "confirmed"
    event_validator.validate(body["maintenance_verified_event"])
