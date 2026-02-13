"""HTTP routes for forecast service."""

from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import get_settings
from .events import build_asset_failure_predicted_event
from .observability import get_metrics, log_event
from .predictor import PredictorFactory, SurrogateLSTMPredictor
from .preprocessing import SensorNormalizer, SequenceBuilder
from .schemas import ForecastRequest, ForecastResponse, HealthResponse, ModelSpecResponse

router = APIRouter()
logger = logging.getLogger("lstm_forecast")

_settings = get_settings()
_normalizer = SensorNormalizer(_settings)
_sequence_builder = SequenceBuilder(_settings, _normalizer)
_metrics = get_metrics()

try:
    _predictor = PredictorFactory.create(_settings)
except Exception as exc:
    if _settings.predictor_mode.strip().lower() == "surrogate":
        _predictor = SurrogateLSTMPredictor()
    elif _settings.fallback_to_surrogate_on_startup_error:
        _predictor = SurrogateLSTMPredictor()
        log_event(
            logger,
            "forecast_predictor_fallback",
            requested_mode=_settings.predictor_mode,
            fallback_mode="surrogate",
            error=str(exc),
        )
    else:
        raise


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


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


@router.get("/model/spec", response_model=ModelSpecResponse)
def model_spec() -> ModelSpecResponse:
    predictor_name = _predictor.__class__.__name__
    if predictor_name == "KerasLSTMPredictor":
        mode = "keras"
    elif predictor_name == "TorchLSTMPredictor":
        mode = "torch"
    else:
        mode = "surrogate"
    architecture = getattr(_predictor, "ARCHITECTURE", SurrogateLSTMPredictor.ARCHITECTURE)
    notes = "Training is intentionally out of scope; this endpoint describes inference expectations."
    return ModelSpecResponse(mode=mode, architecture=architecture, notes=notes)


@router.post("/forecast", response_model=ForecastResponse)
def forecast(payload: ForecastRequest, request: Request):
    started = perf_counter()
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    if _settings.metrics_enabled:
        _metrics.record_request()

    log_event(
        logger,
        "forecast_request",
        asset_id=payload.asset_id,
        trace_id=trace_id,
        horizon_hours=payload.horizon_hours,
        history_points=len(payload.history),
    )

    if payload.horizon_hours != _settings.horizon_hours:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        return _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "UNPROCESSABLE_ENTITY",
            f"Only {_settings.horizon_hours}-hour horizon is supported",
        )

    try:
        sequence = _sequence_builder.build_last_48h_sequence(payload.history)
        result = _predictor.predict(sequence)
    except ValueError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "UNPROCESSABLE_ENTITY", str(exc))
    except RuntimeError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_error(latency_ms)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "MODEL_ERROR", str(exc))

    generated_at = datetime.now(tz=timezone.utc)
    event = build_asset_failure_predicted_event(
        asset_id=payload.asset_id,
        generated_at=generated_at,
        horizon_hours=_settings.horizon_hours,
        result=result,
        trace_id=trace_id,
        produced_by=_settings.event_produced_by,
    )
    latency_ms = (perf_counter() - started) * 1000.0
    if _settings.metrics_enabled:
        _metrics.record_success(latency_ms, result.failure_probability)

    log_event(
        logger,
        "asset_failure_predicted_event",
        asset_id=payload.asset_id,
        trace_id=trace_id,
        failure_probability_72h=result.failure_probability,
        confidence=result.confidence,
        model_mode=result.model_mode,
        latency_ms=round(latency_ms, 3),
    )

    return {
        "data": {
            "asset_id": payload.asset_id,
            "generated_at": generated_at,
            "horizon_hours": _settings.horizon_hours,
            "failure_probability_72h": result.failure_probability,
            "confidence": result.confidence,
            "time_steps_used": len(sequence),
            "features_used": _sequence_builder.FEATURES,
            "normalized": True,
            "model": {
                "name": result.model_name,
                "version": result.model_version,
                "mode": result.model_mode,
                "architecture": result.architecture,
            },
        }
    }
