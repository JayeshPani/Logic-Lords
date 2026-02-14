"""Sensor ingestion service with Firebase telemetry integration."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Literal
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    service_name: str = "sensor-ingestion-service"
    service_version: str = "1.0.0"
    firebase_db_url: str = ""
    firebase_auth_token: str | None = None
    firebase_path_prefix: str = "infraguard"
    firebase_timeout_seconds: float = 8.0
    telemetry_window_size: int = 8

    model_config = SettingsConfigDict(env_prefix="SENSOR_INGESTION_", extra="ignore")

    @property
    def firebase_configured(self) -> bool:
        return bool(self.firebase_db_url.strip())


class Dht11Reading(BaseModel):
    temperature_c: float
    humidity_pct: float = Field(ge=0, le=100)


class AccelerometerReading(BaseModel):
    x_g: float
    y_g: float
    z_g: float


class RawTelemetryReading(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    captured_at: datetime = Field(default_factory=_utc_now)
    firmware_version: str | None = None
    dht11: Dht11Reading
    accelerometer: AccelerometerReading


class SensorCardMetric(BaseModel):
    value: float
    unit: str
    delta: str
    samples: list[float] = Field(default_factory=list)


class ComputedTelemetry(BaseModel):
    acceleration_magnitude_g: float
    vibration_rms_ms2: float
    tilt_deg: float
    strain_proxy_microstrain: float
    thermal_stress_index: float = Field(ge=0, le=1)
    fatigue_index: float = Field(ge=0, le=1)
    health_proxy_score: float = Field(ge=0, le=1)


class AssetTelemetrySnapshot(BaseModel):
    asset_id: str
    source: Literal["firebase"] = "firebase"
    captured_at: datetime
    sensors: dict[str, SensorCardMetric]
    computed: ComputedTelemetry


class IngestTelemetryResponse(BaseModel):
    asset_id: str
    source: Literal["firebase"] = "firebase"
    captured_at: datetime
    latest_path: str
    history_path: str


settings = Settings()
app = FastAPI(title=settings.service_name, version=settings.service_version)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _metric_delta(samples: list[float], precision: int, label: str) -> str:
    if len(samples) < 2:
        return f"+0.{('0' * precision)} {label}"
    delta = samples[-1] - samples[-2]
    sign = "+" if delta >= 0 else "-"
    return f"{sign}{abs(delta):.{precision}f} {label}"


def _firebase_path(*parts: str) -> str:
    normalized = [settings.firebase_path_prefix.strip("/")]
    normalized.extend(part.strip("/") for part in parts if part)
    return "/".join(part for part in normalized if part)


def _firebase_url(path: str, query: dict[str, str] | None = None) -> str:
    base = settings.firebase_db_url.strip().rstrip("/")
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Firebase is not configured. Set SENSOR_INGESTION_FIREBASE_DB_URL.",
        )

    params = dict(query or {})
    if settings.firebase_auth_token:
        params["auth"] = settings.firebase_auth_token

    url = f"{base}/{path.strip('/')}.json"
    if params:
        url = f"{url}?{url_parse.urlencode(params)}"
    return url


def _firebase_request(method: str, path: str, payload: dict | None = None, query: dict[str, str] | None = None) -> object:
    url = _firebase_url(path, query=query)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = url_request.Request(
        url=url,
        method=method,
        data=body,
        headers={"content-type": "application/json"},
    )
    try:
        with url_request.urlopen(request, timeout=max(settings.firebase_timeout_seconds, 0.1)) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except url_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(
            status_code=502,
            detail=f"Firebase HTTP {exc.code}: {detail[:180]}",
        ) from exc
    except url_error.URLError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Firebase unreachable: {exc.reason}",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Firebase request timed out after {settings.firebase_timeout_seconds:.1f}s.",
        ) from exc


def _fetch_records(asset_id: str) -> list[RawTelemetryReading]:
    latest_path = _firebase_path("telemetry", asset_id, "latest")
    history_path = _firebase_path("telemetry", asset_id, "history")

    latest_payload = _firebase_request("GET", latest_path)
    history_payload = _firebase_request(
        "GET",
        history_path,
        query={
            "orderBy": '"$key"',
            "limitToLast": str(max(settings.telemetry_window_size, 2)),
        },
    )

    records: list[RawTelemetryReading] = []
    if isinstance(history_payload, dict):
        for value in history_payload.values():
            if not isinstance(value, dict):
                continue
            try:
                records.append(RawTelemetryReading.model_validate(value))
            except ValidationError:
                continue

    if isinstance(latest_payload, dict) and latest_payload:
        try:
            latest_record = RawTelemetryReading.model_validate(latest_payload)
            records.append(latest_record)
        except ValidationError:
            pass

    records.sort(key=lambda item: item.captured_at)
    deduped: list[RawTelemetryReading] = []
    seen: set[tuple[str, datetime]] = set()
    for record in records:
        marker = (record.device_id, record.captured_at)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(record)

    return deduped[-max(settings.telemetry_window_size, 2) :]


def _build_snapshot(asset_id: str, records: list[RawTelemetryReading]) -> AssetTelemetrySnapshot:
    if not records:
        raise HTTPException(status_code=404, detail=f"No telemetry records found for asset: {asset_id}")

    temperatures = [_safe_float(item.dht11.temperature_c) for item in records]
    humidities = [_safe_float(item.dht11.humidity_pct) for item in records]
    accel_magnitudes = [
        math.sqrt(
            (_safe_float(item.accelerometer.x_g) ** 2)
            + (_safe_float(item.accelerometer.y_g) ** 2)
            + (_safe_float(item.accelerometer.z_g) ** 2)
        )
        for item in records
    ]

    vibration_ms2_samples = [abs(value - 1.0) * 9.80665 for value in accel_magnitudes]
    tilt_deg_samples = [
        math.degrees(math.acos(_clamp((_safe_float(item.accelerometer.z_g) / max(mag, 0.0001)), -1.0, 1.0)))
        for item, mag in zip(records, accel_magnitudes, strict=False)
    ]
    strain_proxy_samples = [value * 16.0 for value in vibration_ms2_samples]

    latest_index = len(records) - 1
    latest_temp = temperatures[latest_index]
    latest_humidity = humidities[latest_index]
    latest_magnitude = accel_magnitudes[latest_index]
    latest_vibration_ms2 = vibration_ms2_samples[latest_index]
    latest_tilt_deg = tilt_deg_samples[latest_index]
    latest_strain = strain_proxy_samples[latest_index]

    thermal_stress_index = _clamp(((latest_temp - 24.0) / 16.0) + max(0.0, (latest_humidity - 60.0) / 120.0), 0.0, 1.0)
    fatigue_index = _clamp(latest_vibration_ms2 / 6.5, 0.0, 1.0)
    tilt_penalty = _clamp(latest_tilt_deg / 45.0, 0.0, 1.0)
    health_proxy_score = _clamp(1.0 - ((0.45 * thermal_stress_index) + (0.45 * fatigue_index) + (0.10 * tilt_penalty)), 0.0, 1.0)

    sensors = {
        "strain": SensorCardMetric(
            value=round(latest_strain, 1),
            unit="me",
            delta=_metric_delta(strain_proxy_samples, 1, "variance"),
            samples=[round(value, 2) for value in strain_proxy_samples[-8:]],
        ),
        "vibration": SensorCardMetric(
            value=round(latest_vibration_ms2, 2),
            unit="mm/s",
            delta=_metric_delta(vibration_ms2_samples, 2, "trend"),
            samples=[round(value, 3) for value in vibration_ms2_samples[-8:]],
        ),
        "temperature": SensorCardMetric(
            value=round(latest_temp, 1),
            unit="C",
            delta=_metric_delta(temperatures, 1, "spike"),
            samples=[round(value, 2) for value in temperatures[-8:]],
        ),
        "tilt": SensorCardMetric(
            value=round(latest_tilt_deg, 2),
            unit="deg",
            delta=_metric_delta(tilt_deg_samples, 2, "drift"),
            samples=[round(value, 3) for value in tilt_deg_samples[-8:]],
        ),
        "humidity": SensorCardMetric(
            value=round(latest_humidity, 1),
            unit="%",
            delta=_metric_delta(humidities, 1, "humidity"),
            samples=[round(value, 2) for value in humidities[-8:]],
        ),
    }

    computed = ComputedTelemetry(
        acceleration_magnitude_g=round(latest_magnitude, 5),
        vibration_rms_ms2=round(latest_vibration_ms2, 5),
        tilt_deg=round(latest_tilt_deg, 4),
        strain_proxy_microstrain=round(latest_strain, 3),
        thermal_stress_index=round(thermal_stress_index, 4),
        fatigue_index=round(fatigue_index, 4),
        health_proxy_score=round(health_proxy_score, 4),
    )

    return AssetTelemetrySnapshot(
        asset_id=asset_id,
        source="firebase",
        captured_at=records[-1].captured_at,
        sensors=sensors,
        computed=computed,
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "firebase_configured": settings.firebase_configured,
        "timestamp": _utc_now().isoformat(),
    }


@app.get("/telemetry/assets/{asset_id}/latest", response_model=AssetTelemetrySnapshot)
def get_asset_latest_telemetry(asset_id: str) -> AssetTelemetrySnapshot:
    records = _fetch_records(asset_id)
    return _build_snapshot(asset_id, records)


@app.post("/telemetry/assets/{asset_id}/ingest", response_model=IngestTelemetryResponse)
def ingest_asset_telemetry(
    asset_id: str,
    payload: RawTelemetryReading,
    persist_history: bool = Query(default=True),
) -> IngestTelemetryResponse:
    latest_path = _firebase_path("telemetry", asset_id, "latest")
    history_path = _firebase_path("telemetry", asset_id, "history")
    encoded = json.loads(payload.model_dump_json())

    _firebase_request("PUT", latest_path, payload=encoded)
    if persist_history:
        _firebase_request("POST", history_path, payload=encoded)

    return IngestTelemetryResponse(
        asset_id=asset_id,
        source="firebase",
        captured_at=payload.captured_at,
        latest_path=latest_path,
        history_path=history_path,
    )
