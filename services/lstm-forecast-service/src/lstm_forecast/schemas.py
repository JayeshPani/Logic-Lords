"""Pydantic schemas for forecast API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RawSensorRecord(BaseModel):
    """Raw sensor record used by the forecast pipeline."""

    strain_value: float
    vibration_rms: float
    temperature: float
    humidity: float = Field(ge=0, le=100)
    traffic_density: float | None = None
    rainfall_intensity: float | None = None
    timestamp: datetime


class ForecastRequest(BaseModel):
    """Request payload for 72-hour failure forecasting."""

    asset_id: str = Field(min_length=1)
    history: list[RawSensorRecord] = Field(min_length=2)
    horizon_hours: int = Field(default=72, ge=1, le=168)


class ForecastModelInfo(BaseModel):
    """Metadata for the predictor in use."""

    name: str
    version: str
    mode: Literal["surrogate", "keras", "torch"]
    architecture: list[str]


class ForecastData(BaseModel):
    """Forecast response payload."""

    asset_id: str
    generated_at: datetime
    horizon_hours: int
    failure_probability_72h: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    time_steps_used: int
    features_used: list[str]
    normalized: bool
    model: ForecastModelInfo


class ForecastResponse(BaseModel):
    """Envelope for forecast response."""

    data: ForecastData


class ModelSpecResponse(BaseModel):
    """Model architecture spec response."""

    mode: Literal["surrogate", "keras", "torch"]
    architecture: list[str]
    notes: str


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
