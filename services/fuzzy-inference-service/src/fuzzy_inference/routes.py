"""HTTP routes for fuzzy inference service."""

from datetime import datetime, timezone

from fastapi import APIRouter

from .config import get_settings
from .engine import MamdaniFuzzyEngine
from .schemas import FuzzyInferRequest, FuzzyInferResponse, HealthResponse

router = APIRouter()

_settings = get_settings()
_engine = MamdaniFuzzyEngine(_settings)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.post("/infer", response_model=FuzzyInferResponse)
def infer(payload: FuzzyInferRequest) -> FuzzyInferResponse:
    result = _engine.evaluate(payload.inputs)
    return FuzzyInferResponse(
        data={
            "asset_id": payload.asset_id,
            "evaluated_at": payload.evaluated_at or datetime.now(tz=timezone.utc),
            "final_risk_score": result.final_risk_score,
            "risk_level": result.risk_level,
            "rule_activations": result.rule_activations,
            "method": "mamdani_centroid",
        }
    )
