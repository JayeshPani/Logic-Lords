"""HTTP routes for API gateway facade."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import socket
from typing import Annotated
from urllib import error as url_error
from urllib import request as url_request

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .errors import ApiError, build_meta
from .observability import get_metrics, log_event
from .schemas import (
    AssetListResponse,
    AssetTelemetry,
    AssetTelemetryResponse,
    AssetResponse,
    AssetForecastResponse,
    AssetHealthResponse,
    BlockchainConnectResponse,
    CreateAssetRequest,
    DependencyHealth,
    HealthCheckResponse,
    MaintenanceVerificationResponse,
    Pagination,
)
from .security import AuthContext, enforce_rate_limit, get_auth_context
from .store import get_store

router = APIRouter()
logger = logging.getLogger("api_gateway")

_settings = get_settings()
_metrics = get_metrics()
_store = get_store()


def _trace_id(request: Request) -> str:
    return request.headers.get("x-trace-id") or f"trc_{datetime.now(tz=timezone.utc).strftime('%H%M%S%f')[:12]}"


def _with_metrics(path: str) -> None:
    if _settings.metrics_enabled:
        _metrics.record_request(path)


def _connect_blockchain_service(trace_id: str) -> dict:
    timeout_seconds = max(_settings.blockchain_connect_timeout_seconds, 0.1)
    attempts: list[str] = []
    timed_out = False

    for base_url in _settings.blockchain_verification_urls:
        endpoint = f"{base_url.rstrip('/')}/onchain/connect"
        request = url_request.Request(
            url=endpoint,
            data=b"{}",
            method="POST",
            headers={
                "content-type": "application/json",
                "x-trace-id": trace_id,
            },
        )
        try:
            with url_request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            if exc.code in {404, 405}:
                attempts.append(f"{base_url} -> HTTP {exc.code}")
                continue
            raise ApiError(
                status_code=502,
                code="BLOCKCHAIN_SERVICE_ERROR",
                message=f"Blockchain service HTTP {exc.code}: {details[:180]}",
                trace_id=trace_id,
            ) from exc
        except url_error.URLError as exc:
            attempts.append(f"{base_url} -> {exc.reason}")
            continue
        except (TimeoutError, socket.timeout):
            timed_out = True
            attempts.append(f"{base_url} -> timeout")
            continue
        except OSError as exc:
            attempts.append(f"{base_url} -> {exc}")
            continue

        try:
            body = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiError(
                status_code=502,
                code="BLOCKCHAIN_BAD_RESPONSE",
                message="Blockchain service returned invalid JSON.",
                trace_id=trace_id,
            ) from exc

        if not isinstance(body, dict):
            raise ApiError(
                status_code=502,
                code="BLOCKCHAIN_BAD_RESPONSE",
                message="Blockchain service returned an unsupported payload shape.",
                trace_id=trace_id,
            )
        return body

    summary = "; ".join(attempts[:3]) or "no endpoint attempts recorded"
    if timed_out and not attempts:
        raise ApiError(
            status_code=504,
            code="BLOCKCHAIN_TIMEOUT",
            message=f"Blockchain service timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        )

    if timed_out and attempts and all(attempt.endswith("timeout") for attempt in attempts):
        raise ApiError(
            status_code=504,
            code="BLOCKCHAIN_TIMEOUT",
            message=f"Blockchain service timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        )

    raise ApiError(
        status_code=503,
        code="BLOCKCHAIN_UNAVAILABLE",
        message=f"Blockchain service unreachable. Tried: {summary}",
        trace_id=trace_id,
    )


def _fetch_sensor_telemetry(asset_id: str, trace_id: str) -> dict:
    endpoint = (
        f"{_settings.sensor_ingestion_base_url.rstrip('/')}"
        f"/telemetry/assets/{asset_id}/latest"
    )
    request = url_request.Request(
        url=endpoint,
        method="GET",
        headers={
            "accept": "application/json",
            "x-trace-id": trace_id,
        },
    )

    timeout_seconds = max(_settings.sensor_telemetry_timeout_seconds, 0.1)

    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 404:
            raise ApiError(
                status_code=404,
                code="NOT_FOUND",
                message=f"Telemetry unavailable for asset: {asset_id}",
                trace_id=trace_id,
            ) from exc
        raise ApiError(
            status_code=502,
            code="SENSOR_INGESTION_ERROR",
            message=f"Sensor ingestion HTTP {exc.code}: {details[:180]}",
            trace_id=trace_id,
        ) from exc
    except url_error.URLError as exc:
        raise ApiError(
            status_code=503,
            code="SENSOR_INGESTION_UNAVAILABLE",
            message=f"Sensor ingestion service unreachable: {exc.reason}",
            trace_id=trace_id,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ApiError(
            status_code=504,
            code="SENSOR_INGESTION_TIMEOUT",
            message=f"Sensor ingestion service timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        ) from exc
    except OSError as exc:
        raise ApiError(
            status_code=503,
            code="SENSOR_INGESTION_UNAVAILABLE",
            message=f"Sensor ingestion network error: {exc}",
            trace_id=trace_id,
        ) from exc

    try:
        body = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApiError(
            status_code=502,
            code="SENSOR_INGESTION_BAD_RESPONSE",
            message="Sensor ingestion service returned invalid JSON.",
            trace_id=trace_id,
        ) from exc

    if not isinstance(body, dict):
        raise ApiError(
            status_code=502,
            code="SENSOR_INGESTION_BAD_RESPONSE",
            message="Sensor ingestion service returned an unsupported payload shape.",
            trace_id=trace_id,
        )
    return body


@router.get("/health", response_model=HealthCheckResponse)
def health(request: Request) -> HealthCheckResponse:
    trace_id = _trace_id(request)
    _with_metrics("/health")

    dependencies = {
        "database": DependencyHealth(status="ok", latency_ms=6),
        "event_stream": DependencyHealth(status="ok", latency_ms=4),
        "blockchain_verifier": DependencyHealth(status="ok", latency_ms=7),
    }

    log_event(logger, "gateway_health", trace_id=trace_id)
    return HealthCheckResponse(
        status="ok",
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
        dependencies=dependencies,
    )


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    if not _settings.metrics_enabled:
        raise ApiError(status_code=404, code="NOT_FOUND", message="metrics endpoint disabled")
    return _metrics.render_prometheus()


@router.get("/assets", response_model=AssetListResponse)
def list_assets(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    zone: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> AssetListResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/assets")

    items = _store.list_assets(zone=zone, asset_type=asset_type, status=status)
    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    log_event(logger, "gateway_assets_list", trace_id=trace_id, page=page, page_size=page_size)
    return AssetListResponse(
        data=page_items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
        meta=build_meta(),
    )


@router.post("/assets", response_model=AssetResponse, status_code=201)
def create_asset(
    request: Request,
    payload: CreateAssetRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AssetResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/assets:post")

    try:
        asset = _store.create_asset(payload)
    except ValueError as exc:
        raise ApiError(status_code=409, code="CONFLICT", message=str(exc), trace_id=trace_id) from exc

    log_event(logger, "gateway_asset_created", trace_id=trace_id, asset_id=asset.asset_id)
    return AssetResponse(data=asset, meta=build_meta())


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AssetResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/assets/{asset_id}")

    asset = _store.get_asset(asset_id)
    if asset is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Resource not found.", trace_id=trace_id)

    return AssetResponse(data=asset, meta=build_meta())


@router.get("/assets/{asset_id}/health", response_model=AssetHealthResponse)
def get_asset_health(
    asset_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AssetHealthResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/assets/{asset_id}/health")

    health = _store.get_asset_health(asset_id)
    if health is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Resource not found.", trace_id=trace_id)

    return AssetHealthResponse(data=health, meta=build_meta())


@router.get("/assets/{asset_id}/forecast", response_model=AssetForecastResponse)
def get_asset_forecast(
    asset_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    horizon_hours: int = Query(default=72, ge=1, le=168),
) -> AssetForecastResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/assets/{asset_id}/forecast")

    forecast = _store.get_asset_forecast(asset_id, horizon_hours=horizon_hours)
    if forecast is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Resource not found.", trace_id=trace_id)

    return AssetForecastResponse(data=forecast, meta=build_meta())


@router.get("/maintenance/{maintenance_id}/verification", response_model=MaintenanceVerificationResponse)
def get_maintenance_verification(
    maintenance_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MaintenanceVerificationResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/maintenance/{maintenance_id}/verification")

    verification = _store.get_maintenance_verification(maintenance_id)
    if verification is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Resource not found.", trace_id=trace_id)

    return MaintenanceVerificationResponse(data=verification, meta=build_meta())


@router.post("/blockchain/connect", response_model=BlockchainConnectResponse)
def connect_blockchain(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> BlockchainConnectResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/blockchain/connect")

    payload = _connect_blockchain_service(trace_id)
    payload["source"] = "services/blockchain-verification-service"

    try:
        status = BlockchainConnectResponse.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="BLOCKCHAIN_BAD_RESPONSE",
            message=f"Blockchain service response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc

    log_event(
        logger,
        "gateway_blockchain_connect",
        trace_id=trace_id,
        connected=status.connected,
        chain_id=status.chain_id,
        expected_chain_id=status.expected_chain_id,
        latest_block=status.latest_block,
    )

    return status


@router.get("/telemetry/{asset_id}/latest", response_model=AssetTelemetryResponse)
def get_latest_telemetry(
    asset_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AssetTelemetryResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/telemetry/{asset_id}/latest")

    payload = _fetch_sensor_telemetry(asset_id, trace_id)

    try:
        telemetry = AssetTelemetry.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="SENSOR_INGESTION_BAD_RESPONSE",
            message=f"Sensor telemetry response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc

    log_event(
        logger,
        "gateway_asset_telemetry",
        trace_id=trace_id,
        asset_id=telemetry.asset_id,
        source=telemetry.source,
        captured_at=telemetry.captured_at.isoformat(),
    )
    return AssetTelemetryResponse(data=telemetry, meta=build_meta())
