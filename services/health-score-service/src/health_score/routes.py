"""HTTP routes for health score service."""

from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import OutputComposer
from .events import build_asset_risk_computed_event
from .observability import get_metrics, log_event
from .schemas import ComposeOutputRequest, ComposeOutputResponse, HealthResponse

router = APIRouter()
logger = logging.getLogger("health_score")

_settings = get_settings()
_composer = OutputComposer()
_metrics = get_metrics()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    if not _settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics endpoint disabled")
    return _metrics.render_prometheus()


@router.post("/compose", response_model=ComposeOutputResponse)
def compose(payload: ComposeOutputRequest, request: Request) -> ComposeOutputResponse:
    started = perf_counter()
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    if _settings.metrics_enabled:
        _metrics.record_request()

    log_event(
        logger,
        "health_score_compose_request",
        asset_id=payload.asset_id,
        trace_id=trace_id,
        final_risk_score=payload.final_risk_score,
        failure_probability_72h=payload.failure_probability_72h,
        anomaly_flag=payload.anomaly_flag,
    )

    try:
        output = _composer.compose(payload.final_risk_score)
        evaluated_at = payload.timestamp or datetime.now(tz=timezone.utc)
        event = build_asset_risk_computed_event(
            asset_id=payload.asset_id,
            evaluated_at=evaluated_at,
            health_score=output.health_score,
            risk_level=output.risk_level,
            failure_probability_72h=payload.failure_probability_72h,
            anomaly_flag=payload.anomaly_flag,
            trace_id=trace_id,
            produced_by=_settings.event_produced_by,
        )
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_success(latency_ms, output.health_score)
        log_event(
            logger,
            "asset_risk_computed_event",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            health_score=output.health_score,
            risk_level=output.risk_level,
            anomaly_flag=event["data"]["anomaly_flag"],
            latency_ms=round(latency_ms, 3),
        )
    except Exception as exc:  # pragma: no cover
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        log_event(
            logger,
            "health_score_compose_error",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            latency_ms=round(latency_ms, 3),
            error=str(exc),
        )
        raise

    return ComposeOutputResponse(
        health_score=output.health_score,
        failure_probability_72h=payload.failure_probability_72h,
        anomaly_flag=payload.anomaly_flag,
        risk_level=output.risk_level,
        timestamp=evaluated_at,
    )
