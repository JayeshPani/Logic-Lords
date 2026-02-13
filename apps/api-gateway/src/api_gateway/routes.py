"""HTTP routes for API gateway facade."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .errors import ApiError, build_meta
from .observability import get_metrics, log_event
from .schemas import (
    AssetListResponse,
    AssetResponse,
    AssetForecastResponse,
    AssetHealthResponse,
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
