"""HTTP routes for health score service."""

from datetime import datetime, timezone

from fastapi import APIRouter

from .config import get_settings
from .engine import OutputComposer
from .schemas import ComposeOutputRequest, ComposeOutputResponse, HealthResponse

router = APIRouter()

_settings = get_settings()
_composer = OutputComposer()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.post("/compose", response_model=ComposeOutputResponse)
def compose(payload: ComposeOutputRequest) -> ComposeOutputResponse:
    output = _composer.compose(payload.final_risk_score)
    return ComposeOutputResponse(
        health_score=output.health_score,
        failure_probability_72h=payload.failure_probability_72h,
        anomaly_flag=payload.anomaly_flag,
        risk_level=output.risk_level,
        timestamp=payload.timestamp or datetime.now(tz=timezone.utc),
    )
