"""Pydantic schemas for API gateway contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AssetType = Literal["bridge", "road", "tunnel", "flyover", "other"]
AssetStatus = Literal["active", "maintenance", "retired"]
Severity = Literal["healthy", "watch", "warning", "critical"]
RiskLevel = Literal["Very Low", "Low", "Moderate", "High", "Critical"]
VerificationStatus = Literal["pending", "submitted", "confirmed", "failed"]


class ApiMeta(BaseModel):
    """Standard response metadata."""

    request_id: str = Field(min_length=8, max_length=128)
    timestamp: datetime


class ErrorDetail(BaseModel):
    """Field-level validation detail."""

    field: str
    issue: str


class ErrorBody(BaseModel):
    """Error payload body."""

    code: str
    message: str
    trace_id: str | None = None
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: ErrorBody


class DependencyHealth(BaseModel):
    """Health details for one dependency."""

    status: Literal["ok", "degraded", "down"]
    latency_ms: int | None = Field(default=None, ge=0)


class HealthCheckResponse(BaseModel):
    """Gateway health response."""

    status: Literal["ok", "degraded"]
    service: str
    version: str
    timestamp: datetime
    dependencies: dict[str, DependencyHealth] | None = None


class GeoPoint(BaseModel):
    """Geographic coordinate."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Asset(BaseModel):
    """Asset representation."""

    asset_id: str = Field(pattern=r"^asset_[a-z0-9]+_[a-z0-9]+_[0-9]+$")
    name: str = Field(min_length=2, max_length=120)
    asset_type: AssetType
    status: AssetStatus
    zone: str = Field(min_length=1, max_length=64)
    location: GeoPoint
    metadata: dict[str, object] = Field(default_factory=dict)
    installed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateAssetRequest(BaseModel):
    """Request payload for asset creation."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(pattern=r"^asset_[a-z0-9]+_[a-z0-9]+_[0-9]+$")
    name: str = Field(min_length=2, max_length=120)
    asset_type: AssetType
    zone: str = Field(min_length=1, max_length=64)
    location: GeoPoint
    metadata: dict[str, object] = Field(default_factory=dict)
    installed_at: datetime | None = None


class Pagination(BaseModel):
    """Pagination metadata."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class AssetResponse(BaseModel):
    """Single asset response."""

    data: Asset
    meta: ApiMeta


class AssetListResponse(BaseModel):
    """Paginated asset list response."""

    data: list[Asset]
    pagination: Pagination
    meta: ApiMeta


class RiskComponents(BaseModel):
    """Risk factor decomposition."""

    mechanical_stress: float = Field(ge=0, le=1)
    thermal_stress: float = Field(ge=0, le=1)
    fatigue: float = Field(ge=0, le=1)
    environmental_exposure: float = Field(ge=0, le=1)


class AssetHealth(BaseModel):
    """Asset health snapshot."""

    asset_id: str
    evaluated_at: datetime
    health_score: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    failure_probability_72h: float = Field(ge=0, le=1)
    anomaly_flag: int = Field(ge=0, le=1)
    severity: Severity | None = None
    components: RiskComponents | None = None
    model_versions: dict[str, str] | None = None


class AssetHealthResponse(BaseModel):
    """Asset health response."""

    data: AssetHealth
    meta: ApiMeta


class ForecastModelInfo(BaseModel):
    """Forecast model details."""

    name: str
    version: str


class AssetForecast(BaseModel):
    """Forecast snapshot."""

    asset_id: str
    generated_at: datetime
    horizon_hours: int = Field(ge=1, le=168)
    failure_probability_72h: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    model: ForecastModelInfo | None = None


class AssetForecastResponse(BaseModel):
    """Asset forecast response."""

    data: AssetForecast
    meta: ApiMeta


class MaintenanceVerification(BaseModel):
    """Verification state for one maintenance action."""

    maintenance_id: str = Field(pattern=r"^mnt_[0-9]{8}_[0-9]+$")
    asset_id: str
    verification_status: VerificationStatus
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    network: str
    contract_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain_id: int = Field(ge=1)
    block_number: int | None = Field(default=None, ge=0)
    verified_at: datetime | None = None


class MaintenanceVerificationResponse(BaseModel):
    """Verification response wrapper."""

    data: MaintenanceVerification
    meta: ApiMeta


class BlockchainConnectResponse(BaseModel):
    """Sepolia connectivity status proxied for dashboard use."""

    connected: bool
    network: Literal["sepolia"] = "sepolia"
    expected_chain_id: int = Field(ge=1)
    chain_id: int | None = Field(default=None, ge=1)
    latest_block: int | None = Field(default=None, ge=0)
    contract_address: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{40}$")
    contract_deployed: bool | None = None
    checked_at: datetime
    message: str
    source: str = "services/blockchain-verification-service"
