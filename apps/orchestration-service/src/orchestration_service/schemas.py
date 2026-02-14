"""Pydantic schemas for orchestration service APIs."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


RiskLevel = Literal["Very Low", "Low", "Moderate", "High", "Critical"]
PriorityLevel = Literal["low", "medium", "high", "critical"]
WorkflowStatus = Literal["started", "inspection_requested", "maintenance_completed", "failed"]
WorkflowVerificationStatus = Literal["awaiting_evidence", "pending", "submitted", "confirmed", "failed"]
EscalationStage = Literal["management_notified", "acknowledged", "police_notified", "maintenance_completed"]


class AssetRiskComputedData(BaseModel):
    """Payload for `asset.risk.computed` event data."""

    asset_id: str = Field(min_length=1)
    evaluated_at: datetime
    health_score: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    failure_probability_72h: float = Field(ge=0, le=1)
    anomaly_flag: int = Field(ge=0, le=1)


class AssetRiskComputedEvent(BaseModel):
    """`asset.risk.computed` event envelope."""

    event_id: UUID
    event_type: Literal["asset.risk.computed"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: AssetRiskComputedData


class AssetFailurePredictedData(BaseModel):
    """Payload for `asset.failure.predicted` event data."""

    asset_id: str = Field(min_length=1)
    generated_at: datetime
    horizon_hours: Literal[72]
    failure_probability_72h: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class AssetFailurePredictedEvent(BaseModel):
    """`asset.failure.predicted` event envelope."""

    event_id: UUID
    event_type: Literal["asset.failure.predicted"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: AssetFailurePredictedData


class InspectionCreatePayload(BaseModel):
    """Payload for `inspection.create` command."""

    asset_id: str = Field(min_length=1)
    priority: PriorityLevel
    reason: str = Field(min_length=3, max_length=500)
    triggered_by_event_id: UUID
    health_score: float | None = Field(default=None, ge=0, le=1)
    failure_probability: float | None = Field(default=None, ge=0, le=1)


class InspectionCreateCommand(BaseModel):
    """`inspection.create` command envelope."""

    command_id: UUID
    command_type: Literal["inspection.create"]
    command_version: str = Field(pattern=r"^v[0-9]+$")
    requested_at: datetime
    requested_by: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, str | int | float | bool | None] | None = None
    payload: InspectionCreatePayload


class InspectionRequestedData(BaseModel):
    """Payload for `inspection.requested` event data."""

    ticket_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    requested_at: datetime
    priority: PriorityLevel
    reason: str = Field(min_length=3, max_length=500)


class InspectionRequestedEvent(BaseModel):
    """`inspection.requested` event envelope."""

    event_id: UUID
    event_type: Literal["inspection.requested"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: InspectionRequestedData


class MaintenanceCompletedData(BaseModel):
    """Payload for `maintenance.completed` event data."""

    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    completed_at: datetime
    performed_by: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=5000)


class MaintenanceCompletedEvent(BaseModel):
    """`maintenance.completed` event envelope."""

    event_id: UUID
    event_type: Literal["maintenance.completed"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: MaintenanceCompletedData


class RiskEventIngestResponse(BaseModel):
    """Response for asset-risk event ingestion."""

    workflow_triggered: bool
    workflow_id: str | None = None
    workflow_status: WorkflowStatus | None = None
    reason: str
    retries_used: int = Field(ge=0)
    escalation_stage: EscalationStage | None = None
    inspection_create_command: InspectionCreateCommand | None = None
    inspection_requested_event: InspectionRequestedEvent | None = None


class ForecastEventIngestResponse(BaseModel):
    """Response for forecast-event ingestion."""

    status: Literal["accepted"] = "accepted"
    asset_id: str


class WorkflowStateResponse(BaseModel):
    """Orchestration workflow state."""

    workflow_id: str
    asset_id: str
    workflow_name: str
    status: WorkflowStatus
    priority: PriorityLevel
    trigger_reason: str
    created_at: datetime
    updated_at: datetime
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    trace_id: str
    trigger_event_id: UUID
    last_error: str | None = None
    inspection_ticket_id: str | None = None
    maintenance_id: str | None = None
    verification_status: WorkflowVerificationStatus | None = None
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None
    escalation_stage: EscalationStage | None = None
    authority_notified_at: datetime | None = None
    authority_ack_deadline_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    ack_notes: str | None = None
    police_notified_at: datetime | None = None
    management_dispatch_ids: list[str] = Field(default_factory=list)
    police_dispatch_ids: list[str] = Field(default_factory=list)
    inspection_create_command: InspectionCreateCommand | None = None
    inspection_requested_event: InspectionRequestedEvent | None = None
    maintenance_completed_event: MaintenanceCompletedEvent | None = None


class WorkflowListResponse(BaseModel):
    """Collection of workflow states."""

    items: list[WorkflowStateResponse]


class CompleteMaintenanceRequest(BaseModel):
    """Input payload to mark a workflow maintenance-complete."""

    performed_by: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=5000)
    operator_wallet_address: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{40}$")
    completed_at: datetime | None = None


class WorkflowVerificationSummary(BaseModel):
    """Verification handoff result captured in workflow state."""

    verification_status: WorkflowVerificationStatus
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None


class CompleteMaintenanceResponse(BaseModel):
    """Response payload for maintenance completion action."""

    workflow_id: str
    workflow_status: WorkflowStatus
    maintenance_completed_event: MaintenanceCompletedEvent
    verification_summary: WorkflowVerificationSummary | None = None


class VerificationSubmitRequest(BaseModel):
    """Submit verification for maintenance ID once evidence is finalized."""

    submitted_by: str = Field(min_length=1, max_length=128)
    operator_wallet_address: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{40}$")


class VerificationSubmitResponse(BaseModel):
    """Verification submit result bound to maintenance ID."""

    workflow_id: str
    maintenance_id: str
    verification_status: WorkflowVerificationStatus
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None


class VerificationStateResponse(BaseModel):
    """Current verification state for one maintenance ID."""

    workflow_id: str
    maintenance_id: str
    verification_status: WorkflowVerificationStatus
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    verification_error: str | None = None
    verification_updated_at: datetime | None = None


class AutomationIncident(BaseModel):
    """Automation incident state rendered in dashboard automation tab."""

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


class IncidentListResponse(BaseModel):
    """Collection of automation incidents."""

    items: list[AutomationIncident]


class AcknowledgementRequest(BaseModel):
    """Dashboard acknowledgement payload."""

    acknowledged_by: str = Field(min_length=1, max_length=128)
    ack_notes: str | None = Field(default=None, max_length=2000)


class AcknowledgementResponse(BaseModel):
    """Acknowledgement result."""

    workflow_id: str
    escalation_stage: EscalationStage
    acknowledged_at: datetime
    acknowledged_by: str
    ack_notes: str | None = None
    police_notified_at: datetime | None = None


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime


class MetricsResponse(BaseModel):
    """Internal helper schema for metrics snapshots."""

    values: dict[str, Any]
