"""HTTP routes for anomaly detection service."""

from datetime import datetime, timezone

from fastapi import APIRouter

from .config import get_settings
from .engine import AnomalyDetector
from .schemas import AnomalyDetectRequest, AnomalyDetectResponse, HealthResponse

router = APIRouter()

_settings = get_settings()
_detector = AnomalyDetector(_settings)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.post("/detect", response_model=AnomalyDetectResponse)
def detect(payload: AnomalyDetectRequest) -> AnomalyDetectResponse:
    result = _detector.detect(payload.current, payload.baseline_window)
    return AnomalyDetectResponse(
        data={
            "asset_id": payload.asset_id,
            "anomaly_score": result.anomaly_score,
            "anomaly_flag": result.anomaly_flag,
            "threshold": result.threshold,
            "detector_mode": result.detector_mode,
            "evaluated_at": datetime.now(tz=timezone.utc),
        }
    )
