"""HTTP routes for forecast service."""

from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .predictor import PredictorFactory, SurrogateLSTMPredictor
from .preprocessing import SensorNormalizer, SequenceBuilder
from .schemas import ForecastRequest, ForecastResponse, HealthResponse, ModelSpecResponse

router = APIRouter()

_settings = get_settings()
_normalizer = SensorNormalizer(_settings)
_sequence_builder = SequenceBuilder(_settings, _normalizer)

try:
    _predictor = PredictorFactory.create(_settings)
except Exception:
    if _settings.predictor_mode.strip().lower() == "surrogate":
        _predictor = SurrogateLSTMPredictor()
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
def forecast(payload: ForecastRequest):
    if payload.horizon_hours != _settings.horizon_hours:
        return _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "UNPROCESSABLE_ENTITY",
            f"Only {_settings.horizon_hours}-hour horizon is supported",
        )

    try:
        sequence = _sequence_builder.build_last_48h_sequence(payload.history)
        result = _predictor.predict(sequence)
    except ValueError as exc:
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "UNPROCESSABLE_ENTITY", str(exc))
    except RuntimeError as exc:
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "MODEL_ERROR", str(exc))

    return {
        "data": {
            "asset_id": payload.asset_id,
            "generated_at": datetime.now(tz=timezone.utc),
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
