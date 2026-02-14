"""Pydantic schemas for API gateway contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AssetType = Literal["bridge", "road", "tunnel", "flyover", "other"]
AssetStatus = Literal["active", "maintenance", "retired"]
Severity = Literal["healthy", "watch", "warning", "critical"]
RiskLevel = Literal["Very Low", "Low", "Moderate", "High", "Critical"]
VerificationStatus = Literal["pending", "submitted", "confirmed", "failed"]
WorkflowVerificationStatus = Literal["awaiting_evidence", "pending", "submitted", "confirmed", "failed"]
EscalationStage = Literal["management_notified", "acknowledged", "police_notified", "maintenance_completed"]
WorkflowStatus = Literal["started", "inspection_requested", "maintenance_completed", "failed"]
PriorityLevel = Literal["low", "medium", "high", "critical"]
EvidenceStatus = Literal["upload_pending", "finalized", "deleted"]


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

    verification_id: str | None = None
    command_id: str | None = None
    maintenance_id: str = Field(pattern=r"^mnt_[0-9]{8}_[0-9]+$")
    asset_id: str
    verification_status: VerificationStatus
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    network: str
    contract_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain_id: int = Field(ge=1)
    block_number: int | None = Field(default=None, ge=0)
    confirmations: int = Field(default=0, ge=0)
    required_confirmations: int = Field(default=1, ge=1)
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    trace_id: str | None = None
    verified_at: datetime | None = None


class MaintenanceVerificationResponse(BaseModel):
    """Verification response wrapper."""

    data: MaintenanceVerification
    meta: ApiMeta


class MaintenanceVerificationTrackResponse(BaseModel):
    """Verification tracking response wrapper."""

    data: MaintenanceVerification
    maintenance_verified_event: dict[str, object] | None = None
    meta: ApiMeta


class EvidenceItem(BaseModel):
    """Uploaded organization evidence record."""

    evidence_id: str = Field(min_length=1)
    maintenance_id: str = Field(pattern=r"^mnt_[0-9]{8}_[0-9]+$")
    asset_id: str
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=1)
    storage_uri: str = Field(min_length=1)
    sha256_hex: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    uploaded_by: str = Field(min_length=1, max_length=128)
    uploaded_at: datetime
    finalized_at: datetime | None = None
    status: EvidenceStatus
    category: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class CreateEvidenceUploadRequest(BaseModel):
    """Request payload to create evidence upload session."""

    asset_id: str
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=1)
    category: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class CreateEvidenceUploadResponse(BaseModel):
    """Evidence upload session details."""

    data: EvidenceItem
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"
    upload_headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    meta: ApiMeta


class FinalizeEvidenceUploadRequest(BaseModel):
    """Finalize evidence upload and compute file hash."""

    uploaded_by: str = Field(min_length=1, max_length=128)


class FinalizeEvidenceUploadResponse(BaseModel):
    """Finalized evidence response."""

    data: EvidenceItem
    meta: ApiMeta


class EvidenceListResponse(BaseModel):
    """List of evidence records for maintenance ID."""

    data: list[EvidenceItem]
    meta: ApiMeta


class VerificationSubmitRequest(BaseModel):
    """Request body to submit verification after evidence upload."""

    operator_wallet_address: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{40}$")
    submitted_by: str | None = Field(default=None, min_length=1, max_length=128)


class VerificationSubmitResult(BaseModel):
    """Submit verification result from orchestration."""

    workflow_id: str
    maintenance_id: str = Field(pattern=r"^mnt_[0-9]{8}_[0-9]+$")
    verification_status: WorkflowVerificationStatus
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None


class VerificationSubmitResponse(BaseModel):
    """Verification submit response wrapper."""

    data: VerificationSubmitResult
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


class SensorCardMetric(BaseModel):
    """Sensor card metric consumed by dashboard UI."""

    value: float
    unit: str
    delta: str
    samples: list[float] = Field(default_factory=list)


class TelemetryComputed(BaseModel):
    """Computed telemetry indexes from sensor stream."""

    acceleration_magnitude_g: float
    vibration_rms_ms2: float
    tilt_deg: float
    strain_proxy_microstrain: float
    thermal_stress_index: float = Field(ge=0, le=1)
    fatigue_index: float = Field(ge=0, le=1)
    health_proxy_score: float = Field(ge=0, le=1)


class AssetTelemetry(BaseModel):
    """Latest telemetry snapshot for one asset."""

    asset_id: str
    source: str
    captured_at: datetime
    sensors: dict[str, SensorCardMetric]
    computed: TelemetryComputed


class AssetTelemetryResponse(BaseModel):
    """Telemetry response wrapper."""

    data: AssetTelemetry
    meta: ApiMeta


class AutomationIncident(BaseModel):
    """Automation incident proxied from orchestration service."""

    workflow_id: str
    asset_id: str
    risk_priority: PriorityLevel
    escalation_stage: EscalationStage
    status: WorkflowStatus
    trigger_reason: str
    created_at: datetime
    updated_at: datetime
    authority_notified_at: datetime | None = None
    authority_ack_deadline_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    ack_notes: str | None = None
    police_notified_at: datetime | None = None
    management_dispatch_ids: list[str] = Field(default_factory=list)
    police_dispatch_ids: list[str] = Field(default_factory=list)
    inspection_ticket_id: str | None = None
    maintenance_id: str | None = None
    verification_status: WorkflowVerificationStatus | None = None
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None


class AutomationIncidentListResponse(BaseModel):
    """Automation incident collection response."""

    data: list[AutomationIncident]
    meta: ApiMeta


class AutomationIncidentResponse(BaseModel):
    """Single automation incident response."""

    data: AutomationIncident
    meta: ApiMeta


class AutomationAcknowledgeRequest(BaseModel):
    """Request payload for incident acknowledgement."""

    acknowledged_by: str = Field(min_length=1, max_length=128)
    ack_notes: str | None = Field(default=None, max_length=2000)


class AutomationAcknowledgeResult(BaseModel):
    """Acknowledgement result payload."""

    workflow_id: str
    escalation_stage: EscalationStage
    acknowledged_at: datetime
    acknowledged_by: str
    ack_notes: str | None = None
    police_notified_at: datetime | None = None


class AutomationAcknowledgeResponse(BaseModel):
    """Acknowledgement response wrapper."""

    data: AutomationAcknowledgeResult
    meta: ApiMeta
