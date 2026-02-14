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
    AutomationAcknowledgeRequest,
    AutomationAcknowledgeResponse,
    AutomationAcknowledgeResult,
    AutomationIncident,
    AutomationIncidentListResponse,
    AutomationIncidentResponse,
    BlockchainConnectResponse,
    CreateEvidenceUploadRequest,
    CreateEvidenceUploadResponse,
    CreateAssetRequest,
    DependencyHealth,
    EvidenceItem,
    EvidenceListResponse,
    FinalizeEvidenceUploadRequest,
    FinalizeEvidenceUploadResponse,
    HealthCheckResponse,
    LstmRealtimeIngestRequest,
    LstmRealtimeResponse,
    MaintenanceVerificationResponse,
    MaintenanceVerification,
    MaintenanceVerificationTrackResponse,
    Pagination,
    VerificationSubmitRequest,
    VerificationSubmitResponse,
    VerificationSubmitResult,
)
from .security import AuthContext, enforce_rate_limit, get_auth_context, require_roles
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


def _request_blockchain_verification(
    *,
    trace_id: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    timeout_seconds = max(_settings.blockchain_verification_timeout_seconds, 0.1)
    attempts: list[str] = []
    timed_out = False

    payload = None
    headers = {
        "accept": "application/json",
        "x-trace-id": trace_id,
    }
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"

    for base_url in _settings.blockchain_verification_urls:
        endpoint = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        request = url_request.Request(
            url=endpoint,
            data=payload,
            method=method,
            headers=headers,
        )

        try:
            with url_request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 404:
                raise ApiError(
                    status_code=404,
                    code="NOT_FOUND",
                    message="Verification record not found.",
                    trace_id=trace_id,
                ) from exc
            if exc.code == 409:
                raise ApiError(
                    status_code=409,
                    code="CONFLICT",
                    message=details[:180] or "Verification request conflict.",
                    trace_id=trace_id,
                ) from exc
            if exc.code in {400, 401, 403}:
                raise ApiError(
                    status_code=exc.code,
                    code="BAD_REQUEST" if exc.code == 400 else "FORBIDDEN",
                    message=details[:180] or f"Verification request failed with HTTP {exc.code}.",
                    trace_id=trace_id,
                ) from exc

            attempts.append(f"{base_url} -> HTTP {exc.code}")
            continue
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
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(
                status_code=502,
                code="BAD_RESPONSE",
                message="Blockchain verification service returned invalid JSON.",
                trace_id=trace_id,
            ) from exc

        if not isinstance(parsed, dict):
            raise ApiError(
                status_code=502,
                code="BAD_RESPONSE",
                message="Blockchain verification service returned unsupported payload shape.",
                trace_id=trace_id,
            )
        return parsed

    if timed_out and attempts and all(attempt.endswith("timeout") for attempt in attempts):
        raise ApiError(
            status_code=504,
            code="TIMEOUT",
            message=f"Blockchain verification timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        )

    summary = "; ".join(attempts[:3]) or "no endpoint attempts recorded"
    raise ApiError(
        status_code=503,
        code="UNAVAILABLE",
        message=f"Blockchain verification service unreachable. Tried: {summary}",
        trace_id=trace_id,
    )


def _parse_maintenance_verification(raw: dict, trace_id: str) -> MaintenanceVerification:
    data = dict(raw)
    if data.get("confirmed_at") and not data.get("verified_at"):
        data["verified_at"] = data["confirmed_at"]

    try:
        validated = MaintenanceVerification.model_validate(data)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="BAD_RESPONSE",
            message=f"Verification response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc

    return validated


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


def _request_orchestration(
    *,
    trace_id: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    base_url = _settings.orchestration_base_url.rstrip("/")
    endpoint = f"{base_url}/{path.lstrip('/')}"
    timeout_seconds = max(_settings.orchestration_timeout_seconds, 0.1)

    payload = None
    headers = {
        "accept": "application/json",
        "x-trace-id": trace_id,
    }
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"

    request = url_request.Request(
        url=endpoint,
        data=payload,
        method=method,
        headers=headers,
    )

    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 404:
            raise ApiError(
                status_code=404,
                code="NOT_FOUND",
                message="Automation incident not found.",
                trace_id=trace_id,
            ) from exc
        if exc.code == 409:
            raise ApiError(
                status_code=409,
                code="CONFLICT",
                message=details[:180] or "Automation request conflict.",
                trace_id=trace_id,
            ) from exc
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_ERROR",
            message=f"Orchestration service HTTP {exc.code}: {details[:180]}",
            trace_id=trace_id,
        ) from exc
    except url_error.URLError as exc:
        raise ApiError(
            status_code=503,
            code="ORCHESTRATION_UNAVAILABLE",
            message=f"Orchestration service unreachable: {exc.reason}",
            trace_id=trace_id,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ApiError(
            status_code=504,
            code="ORCHESTRATION_TIMEOUT",
            message=f"Orchestration service timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        ) from exc
    except OSError as exc:
        raise ApiError(
            status_code=503,
            code="ORCHESTRATION_UNAVAILABLE",
            message=f"Orchestration network error: {exc}",
            trace_id=trace_id,
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message="Orchestration service returned invalid JSON.",
            trace_id=trace_id,
        ) from exc

    if not isinstance(parsed, dict):
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message="Orchestration service returned an unsupported payload shape.",
            trace_id=trace_id,
        )
    return parsed


def _request_report_generation(
    *,
    trace_id: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    base_url = _settings.report_generation_base_url.rstrip("/")
    endpoint = f"{base_url}/{path.lstrip('/')}"
    timeout_seconds = max(_settings.report_generation_timeout_seconds, 0.1)

    payload = None
    headers = {
        "accept": "application/json",
        "x-trace-id": trace_id,
    }
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"

    request = url_request.Request(url=endpoint, data=payload, method=method, headers=headers)

    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 404:
            raise ApiError(
                status_code=404,
                code="NOT_FOUND",
                message="Requested evidence resource not found.",
                trace_id=trace_id,
            ) from exc
        if exc.code == 409:
            message = details[:180] or "Evidence request conflict."
            if "EVIDENCE_REQUIRED" in details:
                message = "EVIDENCE_REQUIRED"
            raise ApiError(
                status_code=409,
                code="CONFLICT",
                message=message,
                trace_id=trace_id,
            ) from exc
        if exc.code in {400, 401, 403}:
            raise ApiError(
                status_code=exc.code,
                code="BAD_REQUEST" if exc.code == 400 else "FORBIDDEN",
                message=details[:180] or f"Report generation request failed with HTTP {exc.code}.",
                trace_id=trace_id,
            ) from exc
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_ERROR",
            message=f"Report generation service HTTP {exc.code}: {details[:180]}",
            trace_id=trace_id,
        ) from exc
    except url_error.URLError as exc:
        raise ApiError(
            status_code=503,
            code="REPORT_GENERATION_UNAVAILABLE",
            message=f"Report generation service unreachable: {exc.reason}",
            trace_id=trace_id,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ApiError(
            status_code=504,
            code="REPORT_GENERATION_TIMEOUT",
            message=f"Report generation service timed out after {timeout_seconds:.1f}s.",
            trace_id=trace_id,
        ) from exc
    except OSError as exc:
        raise ApiError(
            status_code=503,
            code="REPORT_GENERATION_UNAVAILABLE",
            message=f"Report generation network error: {exc}",
            trace_id=trace_id,
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Report generation service returned invalid JSON.",
            trace_id=trace_id,
        ) from exc

    if not isinstance(parsed, dict):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Report generation service returned an unsupported payload shape.",
            trace_id=trace_id,
        )
    return parsed


def _parse_evidence_item(raw: dict, trace_id: str) -> EvidenceItem:
    try:
        return EvidenceItem.model_validate(raw)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message=f"Evidence response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc


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

    payload = _request_blockchain_verification(
        trace_id=trace_id,
        method="GET",
        path=f"/verifications/{maintenance_id}",
    )
    verification = _parse_maintenance_verification(payload, trace_id)
    return MaintenanceVerificationResponse(data=verification, meta=build_meta())


@router.post(
    "/maintenance/{maintenance_id}/verification/track",
    response_model=MaintenanceVerificationTrackResponse,
)
def track_maintenance_verification(
    maintenance_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MaintenanceVerificationTrackResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/maintenance/{maintenance_id}/verification/track")

    payload = _request_blockchain_verification(
        trace_id=trace_id,
        method="POST",
        path=f"/verifications/{maintenance_id}/track",
        body={},
    )

    verification_payload = payload.get("verification")
    if not isinstance(verification_payload, dict):
        raise ApiError(
            status_code=502,
            code="BAD_RESPONSE",
            message="Verification tracking response missing verification payload.",
            trace_id=trace_id,
        )

    verification = _parse_maintenance_verification(verification_payload, trace_id)
    event_payload = payload.get("maintenance_verified_event")
    if event_payload is not None and not isinstance(event_payload, dict):
        raise ApiError(
            status_code=502,
            code="BAD_RESPONSE",
            message="Verification tracking response returned invalid event payload.",
            trace_id=trace_id,
        )

    return MaintenanceVerificationTrackResponse(
        data=verification,
        maintenance_verified_event=event_payload,
        meta=build_meta(),
    )


@router.post(
    "/maintenance/{maintenance_id}/evidence/uploads",
    response_model=CreateEvidenceUploadResponse,
)
def create_maintenance_evidence_upload(
    maintenance_id: str,
    body: CreateEvidenceUploadRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> CreateEvidenceUploadResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    require_roles(request, auth, "organization")
    _with_metrics("/maintenance/{maintenance_id}/evidence/uploads")

    payload = _request_report_generation(
        trace_id=trace_id,
        method="POST",
        path=f"/maintenance/{maintenance_id}/evidence/uploads",
        body={
            **body.model_dump(exclude_none=True),
            "uploaded_by": auth.subject,
        },
    )

    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, dict):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence upload response missing evidence payload.",
            trace_id=trace_id,
        )

    evidence = _parse_evidence_item(evidence_raw, trace_id)
    upload_url = payload.get("upload_url")
    expires_at = payload.get("expires_at")
    if not isinstance(upload_url, str) or not upload_url.strip():
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence upload response missing upload URL.",
            trace_id=trace_id,
        )
    if not isinstance(expires_at, str):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence upload response missing expiry timestamp.",
            trace_id=trace_id,
        )

    headers = payload.get("upload_headers")
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence upload headers payload is invalid.",
            trace_id=trace_id,
        )

    return CreateEvidenceUploadResponse(
        data=evidence,
        upload_url=upload_url,
        upload_method="PUT",
        upload_headers={str(key): str(value) for key, value in headers.items()},
        expires_at=expires_at,
        meta=build_meta(),
    )


@router.post(
    "/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize",
    response_model=FinalizeEvidenceUploadResponse,
)
def finalize_maintenance_evidence_upload(
    maintenance_id: str,
    evidence_id: str,
    body: FinalizeEvidenceUploadRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FinalizeEvidenceUploadResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    require_roles(request, auth, "organization")
    _with_metrics("/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize")

    payload = _request_report_generation(
        trace_id=trace_id,
        method="POST",
        path=f"/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize",
        body=body.model_dump(exclude_none=True),
    )
    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, dict):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence finalize response missing evidence payload.",
            trace_id=trace_id,
        )

    evidence = _parse_evidence_item(evidence_raw, trace_id)
    return FinalizeEvidenceUploadResponse(data=evidence, meta=build_meta())


@router.get(
    "/maintenance/{maintenance_id}/evidence",
    response_model=EvidenceListResponse,
)
def list_maintenance_evidence(
    maintenance_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> EvidenceListResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    require_roles(request, auth, "organization")
    _with_metrics("/maintenance/{maintenance_id}/evidence")

    payload = _request_report_generation(
        trace_id=trace_id,
        method="GET",
        path=f"/maintenance/{maintenance_id}/evidence",
    )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ApiError(
            status_code=502,
            code="REPORT_GENERATION_BAD_RESPONSE",
            message="Evidence list response missing items payload.",
            trace_id=trace_id,
        )

    items = [_parse_evidence_item(item, trace_id) for item in raw_items if isinstance(item, dict)]
    return EvidenceListResponse(data=items, meta=build_meta())


@router.post(
    "/maintenance/{maintenance_id}/verification/submit",
    response_model=VerificationSubmitResponse,
)
def submit_maintenance_verification(
    maintenance_id: str,
    body: VerificationSubmitRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> VerificationSubmitResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    require_roles(request, auth, "organization", "operator")
    _with_metrics("/maintenance/{maintenance_id}/verification/submit")

    payload = _request_orchestration(
        trace_id=trace_id,
        method="POST",
        path=f"/maintenance/{maintenance_id}/verification/submit",
        body={
            **body.model_dump(exclude_none=True),
            "submitted_by": body.submitted_by or auth.subject,
        },
    )
    try:
        result = VerificationSubmitResult.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message=f"Verification submit response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc

    return VerificationSubmitResponse(data=result, meta=build_meta())


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


@router.get("/automation/incidents", response_model=AutomationIncidentListResponse)
def list_automation_incidents(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AutomationIncidentListResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/automation/incidents")

    payload = _request_orchestration(trace_id=trace_id, method="GET", path="/incidents")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message="Invalid incidents payload from orchestration service.",
            trace_id=trace_id,
        )

    try:
        items = [AutomationIncident.model_validate(item) for item in raw_items]
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message=f"Orchestration incidents response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc
    return AutomationIncidentListResponse(data=items, meta=build_meta())


@router.get("/automation/incidents/{workflow_id}", response_model=AutomationIncidentResponse)
def get_automation_incident(
    workflow_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AutomationIncidentResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/automation/incidents/{workflow_id}")

    payload = _request_orchestration(
        trace_id=trace_id,
        method="GET",
        path=f"/incidents/{workflow_id}",
    )
    try:
        incident = AutomationIncident.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message=f"Orchestration incident response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc
    return AutomationIncidentResponse(data=incident, meta=build_meta())


@router.post(
    "/automation/incidents/{workflow_id}/acknowledge",
    response_model=AutomationAcknowledgeResponse,
)
def acknowledge_automation_incident(
    workflow_id: str,
    body: AutomationAcknowledgeRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AutomationAcknowledgeResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/automation/incidents/{workflow_id}/acknowledge")

    payload = _request_orchestration(
        trace_id=trace_id,
        method="POST",
        path=f"/incidents/{workflow_id}/acknowledge",
        body=body.model_dump(exclude_none=True),
    )
    try:
        acknowledgement = AutomationAcknowledgeResult.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=502,
            code="ORCHESTRATION_BAD_RESPONSE",
            message=f"Orchestration acknowledgement response validation failed: {exc.errors()}",
            trace_id=trace_id,
        ) from exc

    log_event(
        logger,
        "gateway_incident_acknowledged",
        trace_id=trace_id,
        workflow_id=workflow_id,
        escalation_stage=acknowledgement.escalation_stage,
        acknowledged_by=acknowledgement.acknowledged_by,
    )
    return AutomationAcknowledgeResponse(data=acknowledgement, meta=build_meta())


@router.post("/lstm/realtime/ingest", status_code=202)
def ingest_lstm_realtime(
    request: Request,
    payload: LstmRealtimeIngestRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> dict[str, str]:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/lstm/realtime/ingest")
    _store.set_lstm_realtime(payload.data)
    log_event(
        logger,
        "gateway_lstm_realtime_ingested",
        trace_id=trace_id,
        asset_id=payload.data.asset_id,
        history_points=len(payload.data.history),
        forecast_points=len(payload.data.forecast_points),
    )
    return {"status": "accepted"}


@router.get("/lstm/realtime", response_model=LstmRealtimeResponse)
def get_lstm_realtime(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> LstmRealtimeResponse:
    trace_id = _trace_id(request)
    enforce_rate_limit(request, auth)
    _with_metrics("/lstm/realtime")
    data = _store.get_lstm_realtime()
    log_event(
        logger,
        "gateway_lstm_realtime_read",
        trace_id=trace_id,
        asset_id=data.asset_id,
    )
    return LstmRealtimeResponse(data=data, meta=build_meta())
