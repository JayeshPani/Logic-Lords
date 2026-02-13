"""Pydantic schemas for anomaly detection API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NormalizedFeatures(BaseModel):
    """Normalized features expected by anomaly detector."""

    strain: float = Field(ge=0, le=1)
    vibration: float = Field(ge=0, le=1)
    temperature: float = Field(ge=0, le=1)
    humidity: float = Field(ge=0, le=1)


class AnomalyDetectRequest(BaseModel):
    """Request payload for anomaly detection."""

    asset_id: str = Field(min_length=1)
    current: NormalizedFeatures
    baseline_window: list[NormalizedFeatures] = Field(default_factory=list)


class AnomalyData(BaseModel):
    """Anomaly detection response payload."""

    asset_id: str
    anomaly_score: float = Field(ge=0, le=1)
    anomaly_flag: int = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    detector_mode: Literal["isolation_forest", "heuristic"]
    evaluated_at: datetime


class AnomalyDetectResponse(BaseModel):
    """Envelope for anomaly detection response."""

    data: AnomalyData


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
