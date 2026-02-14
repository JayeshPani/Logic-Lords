"""Contract tests for API gateway responses against OpenAPI schemas."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "apps/api-gateway/src"))

from api_gateway.main import app  # noqa: E402
from api_gateway import routes as gateway_routes  # noqa: E402
from api_gateway.security import get_rate_limiter  # noqa: E402
from api_gateway.store import get_store  # noqa: E402


AUTH_HEADERS = {"Authorization": "Bearer dev-token", "x-trace-id": "trc_contract_gateway_001"}


def _load_contract_spec() -> dict:
    return yaml.safe_load((ROOT / "contracts/api/openapi.yaml").read_text())


def _resolve_schema(spec: dict, schema: dict) -> dict:
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/components/schemas/"):
            raise AssertionError(f"unsupported ref: {ref}")
        key = ref.split("/")[-1]
        return _resolve_schema(spec, spec["components"]["schemas"][key])

    resolved: dict = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_schema(spec, value)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_schema(spec, item) if isinstance(item, dict) else item for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def _validate(spec: dict, schema_name: str, payload: dict) -> None:
    schema = _resolve_schema(spec, spec["components"]["schemas"][schema_name])
    jsonschema.Draft202012Validator(
        schema=schema,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    ).validate(payload)


def test_gateway_openapi_paths_and_responses() -> None:
    get_store().reset()
    get_rate_limiter().set_limits(limit=100, window_seconds=60)

    spec = _load_contract_spec()
    generated = app.openapi()

    required_paths = {
        "/health": "get",
        "/assets": "get",
        "/assets/{asset_id}": "get",
        "/assets/{asset_id}/health": "get",
        "/assets/{asset_id}/forecast": "get",
        "/telemetry/{asset_id}/latest": "get",
        "/maintenance/{maintenance_id}/verification": "get",
        "/blockchain/connect": "post",
    }
    for path, method in required_paths.items():
        assert path in spec["paths"]
        assert path in generated["paths"]
        assert method in generated["paths"][path]

    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    _validate(spec, "HealthCheckResponse", health.json())

    assets = client.get("/assets", headers=AUTH_HEADERS)
    assert assets.status_code == 200
    _validate(spec, "AssetListResponse", assets.json())

    asset = client.get("/assets/asset_w12_bridge_0042", headers=AUTH_HEADERS)
    assert asset.status_code == 200
    _validate(spec, "AssetResponse", asset.json())

    health_snapshot = client.get("/assets/asset_w12_bridge_0042/health", headers=AUTH_HEADERS)
    assert health_snapshot.status_code == 200
    _validate(spec, "AssetHealthResponse", health_snapshot.json())

    forecast = client.get("/assets/asset_w12_bridge_0042/forecast", headers=AUTH_HEADERS)
    assert forecast.status_code == 200
    _validate(spec, "AssetForecastResponse", forecast.json())

    gateway_routes._fetch_sensor_telemetry = lambda _asset_id, _trace_id: {
        "asset_id": "asset_w12_bridge_0042",
        "source": "firebase",
        "captured_at": "2026-02-14T07:05:00+00:00",
        "sensors": {
            "strain": {"value": 12.9, "unit": "me", "delta": "+0.2 variance", "samples": [12.0, 12.4, 12.7, 12.9]},
            "vibration": {"value": 1.3, "unit": "mm/s", "delta": "+0.1 trend", "samples": [1.0, 1.1, 1.2, 1.3]},
            "temperature": {"value": 28.5, "unit": "C", "delta": "+0.4 spike", "samples": [27.8, 28.0, 28.2, 28.5]},
            "tilt": {"value": 3.1, "unit": "deg", "delta": "+0.2 drift", "samples": [2.6, 2.8, 2.9, 3.1]},
        },
        "computed": {
            "acceleration_magnitude_g": 1.01,
            "vibration_rms_ms2": 1.3,
            "tilt_deg": 3.1,
            "strain_proxy_microstrain": 12.9,
            "thermal_stress_index": 0.31,
            "fatigue_index": 0.20,
            "health_proxy_score": 0.79,
        },
    }

    telemetry = client.get("/telemetry/asset_w12_bridge_0042/latest", headers=AUTH_HEADERS)
    assert telemetry.status_code == 200
    _validate(spec, "AssetTelemetryResponse", telemetry.json())

    verification = client.get("/maintenance/mnt_20260214_0012/verification", headers=AUTH_HEADERS)
    assert verification.status_code == 200
    _validate(spec, "MaintenanceVerificationResponse", verification.json())

    gateway_routes._connect_blockchain_service = lambda _trace_id: {
        "connected": True,
        "network": "sepolia",
        "expected_chain_id": 11155111,
        "chain_id": 11155111,
        "latest_block": 100005,
        "contract_address": "0x" + "1" * 40,
        "contract_deployed": True,
        "checked_at": "2026-02-14T06:10:00+00:00",
        "message": "Connected to Sepolia RPC.",
        "source": "services/blockchain-verification-service",
    }

    connect = client.post("/blockchain/connect", headers=AUTH_HEADERS)
    assert connect.status_code == 200
    _validate(spec, "BlockchainConnectResponse", connect.json())
