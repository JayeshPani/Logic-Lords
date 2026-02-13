"""Pydantic schemas for final AI output formatting."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["Very Low", "Low", "Moderate", "High", "Critical"]


class ComposeOutputRequest(BaseModel):
    """Request payload matching final pipeline state before storage/publish."""

    asset_id: str = Field(min_length=1)
    final_risk_score: float = Field(ge=0, le=1)
    failure_probability_72h: float = Field(ge=0, le=1)
    anomaly_flag: int = Field(ge=0, le=1)
    timestamp: datetime | None = None


class ComposeOutputResponse(BaseModel):
    """Expected output format from AI_INTEGRATION.md."""

    health_score: float = Field(ge=0, le=1)
    failure_probability_72h: float = Field(ge=0, le=1)
    anomaly_flag: int = Field(ge=0, le=1)
    risk_level: RiskLevel
    timestamp: datetime


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
