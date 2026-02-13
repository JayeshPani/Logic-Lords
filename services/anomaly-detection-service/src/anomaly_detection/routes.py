"""HTTP routes for anomaly detection service."""

from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import AnomalyDetector
from .events import build_asset_anomaly_detected_event
from .observability import get_metrics, log_event
from .schemas import AnomalyDetectRequest, AnomalyDetectResponse, HealthResponse

router = APIRouter()
logger = logging.getLogger("anomaly_detection")

_settings = get_settings()
_metrics = get_metrics()
_detector = AnomalyDetector(_settings)


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


@router.post("/detect", response_model=AnomalyDetectResponse)
def detect(payload: AnomalyDetectRequest, request: Request) -> AnomalyDetectResponse:
    started = perf_counter()
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    if _settings.metrics_enabled:
        _metrics.record_request()

    log_event(
        logger,
        "anomaly_detect_request",
        asset_id=payload.asset_id,
        trace_id=trace_id,
        baseline_points=len(payload.baseline_window),
    )

    try:
        result = _detector.detect(payload.current, payload.baseline_window)
        evaluated_at = datetime.now(tz=timezone.utc)
        event = build_asset_anomaly_detected_event(
            asset_id=payload.asset_id,
            evaluated_at=evaluated_at,
            result=result,
            trace_id=trace_id,
            produced_by=_settings.event_produced_by,
        )
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_success(latency_ms, result.anomaly_score)

        log_event(
            logger,
            "asset_anomaly_detected_event",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            anomaly_score=result.anomaly_score,
            anomaly_flag=event["data"]["anomaly_flag"],
            detector_mode=result.detector_mode,
            latency_ms=round(latency_ms, 3),
        )
    except Exception as exc:  # pragma: no cover
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        log_event(
            logger,
            "anomaly_detect_error",
            asset_id=payload.asset_id,
            trace_id=trace_id,
            latency_ms=round(latency_ms, 3),
            error=str(exc),
        )
        raise

    return AnomalyDetectResponse(
        data={
            "asset_id": payload.asset_id,
            "anomaly_score": result.anomaly_score,
            "anomaly_flag": result.anomaly_flag,
            "threshold": result.threshold,
            "detector_mode": result.detector_mode,
            "evaluated_at": evaluated_at,
        }
    )
