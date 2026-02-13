"""HTTP routes for fuzzy inference service."""

from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import MamdaniFuzzyEngine
from .events import build_asset_risk_computed_event
from .observability import get_metrics, log_event
from .schemas import FuzzyInferRequest, FuzzyInferResponse, HealthResponse

router = APIRouter()
logger = logging.getLogger("fuzzy_inference")

_settings = get_settings()
_engine = MamdaniFuzzyEngine(_settings)
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


@router.post("/infer", response_model=FuzzyInferResponse)
def infer(payload: FuzzyInferRequest, request: Request) -> FuzzyInferResponse:
    started = perf_counter()
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    if _settings.metrics_enabled:
        _metrics.record_request()

    log_event(
        logger,
        "fuzzy_infer_request",
        asset_id=payload.asset_id,
        trace_id=trace_id,
    )

    try:
        result = _engine.evaluate(payload.inputs)
        evaluated_at = payload.evaluated_at or datetime.now(tz=timezone.utc)
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_success(latency_ms, result.final_risk_score)

        event = build_asset_risk_computed_event(
            asset_id=payload.asset_id,
            evaluated_at=evaluated_at,
            health_score=result.final_risk_score,
            risk_level=result.risk_level,
            failure_probability_72h=payload.inputs.failure_probability,
            anomaly_score=payload.inputs.anomaly_score,
            anomaly_threshold=_settings.anomaly_flag_threshold,
            trace_id=trace_id,
            produced_by=_settings.event_produced_by,
        )

        log_event(
            logger,
            "asset_risk_computed_event",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            risk_level=result.risk_level,
            final_risk_score=result.final_risk_score,
            failure_probability_72h=payload.inputs.failure_probability,
            anomaly_flag=event["data"]["anomaly_flag"],
            latency_ms=round(latency_ms, 3),
        )

        return FuzzyInferResponse(
            data={
                "asset_id": payload.asset_id,
                "evaluated_at": evaluated_at,
                "final_risk_score": result.final_risk_score,
                "risk_level": result.risk_level,
                "rule_activations": result.rule_activations,
                "method": "mamdani_centroid",
            }
        )
    except Exception as exc:  # pragma: no cover
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        log_event(
            logger,
            "fuzzy_infer_error",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            latency_ms=round(latency_ms, 3),
            error=str(exc),
        )
        raise
