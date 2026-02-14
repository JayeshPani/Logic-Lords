"""Pydantic schemas for report generation service."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ReportType = Literal["inspection", "maintenance_verification"]


class IncludeSensorWindow(BaseModel):
    """Optional sensor time window included in report command."""

    from_: datetime = Field(alias="from")
    to: datetime


class ReportGeneratePayload(BaseModel):
    """Payload for `report.generate` command."""

    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    report_type: ReportType
    include_sensor_window: IncludeSensorWindow | None = None


class ReportGenerateCommand(BaseModel):
    """`report.generate` command envelope."""

    command_id: UUID
    command_type: Literal["report.generate"]
    command_version: str = Field(pattern=r"^v[0-9]+$")
    requested_at: datetime
    requested_by: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, str | int | float | bool | None] | None = None
    payload: ReportGeneratePayload


class InspectionRequestedData(BaseModel):
    """Payload for `inspection.requested` event data."""

    ticket_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    requested_at: datetime
    priority: Literal["low", "medium", "high", "critical"]
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


class SourceTraceRef(BaseModel):
    """Minimal trace reference for bundle lineage."""

    message_id: str = Field(min_length=1)
    message_type: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    produced_by: str = Field(min_length=1)
    occurred_at: datetime


class ReportBundle(BaseModel):
    """Structured report artifact for downstream services."""

    report_id: str = Field(min_length=1)
    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    report_type: ReportType
    generated_at: datetime
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    summary: str = Field(min_length=3, max_length=5000)
    source_traces: list[SourceTraceRef] = Field(min_length=1)
    sections: dict[str, str | int | float | bool | list[str] | dict[str, str]]


class ReportGeneratedData(BaseModel):
    """Payload for `report.generated` event data."""

    report_id: str = Field(min_length=1)
    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    report_type: ReportType
    generated_at: datetime
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    source_trace_ids: list[str] = Field(min_length=1)
    source_event_ids: list[UUID] = Field(min_length=1)


class ReportGeneratedEvent(BaseModel):
    """`report.generated` event envelope."""

    event_id: UUID
    event_type: Literal["report.generated"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: ReportGeneratedData


class VerificationRecordPayload(BaseModel):
    """Payload for `verification.record.blockchain` command."""

    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    network: str = Field(min_length=2, max_length=64)
    contract_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain_id: int = Field(ge=1)


class VerificationRecordBlockchainCommand(BaseModel):
    """`verification.record.blockchain` command envelope."""

    command_id: UUID
    command_type: Literal["verification.record.blockchain"]
    command_version: str = Field(pattern=r"^v[0-9]+$")
    requested_at: datetime
    requested_by: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, str | int | float | bool | None] | None = None
    payload: VerificationRecordPayload


class GenerateReportRequest(BaseModel):
    """API payload to generate a report from command + context."""

    command: ReportGenerateCommand
    generated_at: datetime | None = None


class GenerateReportResponse(BaseModel):
    """API response containing report bundle and downstream messages."""

    report_bundle: ReportBundle
    report_generated_event: ReportGeneratedEvent
    verification_record_command: VerificationRecordBlockchainCommand


class IngestEventResponse(BaseModel):
    """Status response for context event ingestion."""

    status: Literal["accepted"] = "accepted"


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
