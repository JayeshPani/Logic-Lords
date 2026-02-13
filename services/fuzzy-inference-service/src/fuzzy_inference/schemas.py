"""Pydantic schemas for fuzzy inference API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["Very Low", "Low", "Moderate", "High", "Critical"]


class FuzzyInputs(BaseModel):
    """Normalized fuzzy inputs in [0,1]."""

    strain: float = Field(ge=0, le=1)
    vibration: float = Field(ge=0, le=1)
    temperature: float = Field(ge=0, le=1)
    rainfall_intensity: float = Field(ge=0, le=1)
    traffic_density: float = Field(ge=0, le=1)
    failure_probability: float = Field(ge=0, le=1)
    anomaly_score: float = Field(ge=0, le=1)


class FuzzyInferRequest(BaseModel):
    """Request payload for Mamdani fuzzy inference."""

    asset_id: str = Field(min_length=1)
    evaluated_at: datetime | None = None
    inputs: FuzzyInputs


class RuleActivation(BaseModel):
    """Activated fuzzy rule details."""

    name: str
    activation: float = Field(ge=0, le=1)
    consequent: str


class FuzzyInferData(BaseModel):
    """Response payload for fuzzy inference."""

    asset_id: str
    evaluated_at: datetime
    final_risk_score: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    rule_activations: list[RuleActivation]
    method: Literal["mamdani_centroid"] = "mamdani_centroid"


class FuzzyInferResponse(BaseModel):
    """Envelope for fuzzy inference response."""

    data: FuzzyInferData


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
