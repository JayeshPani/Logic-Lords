"""Pydantic schemas for blockchain verification service."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


VerificationStatus = Literal["pending", "submitted", "confirmed", "failed"]


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


class MaintenanceVerifiedBlockchainData(BaseModel):
    """Payload for `maintenance.verified.blockchain` event."""

    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    tx_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    network: str = Field(min_length=2, max_length=64)
    verified_at: datetime


class MaintenanceVerifiedBlockchainEvent(BaseModel):
    """`maintenance.verified.blockchain` event envelope."""

    event_id: UUID
    event_type: Literal["maintenance.verified.blockchain"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: MaintenanceVerifiedBlockchainData


class VerificationRecord(BaseModel):
    """Verification state tracked by the service."""

    verification_id: str = Field(min_length=1)
    command_id: UUID
    maintenance_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    verification_status: VerificationStatus
    evidence_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
    tx_hash: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{64}$")
    network: str = Field(min_length=2, max_length=64)
    contract_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain_id: int = Field(ge=1)
    block_number: int | None = Field(default=None, ge=0)
    confirmations: int = Field(ge=0)
    required_confirmations: int = Field(ge=1)
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    trace_id: str = Field(min_length=8, max_length=128)


class RecordVerificationResponse(BaseModel):
    """Response for initial record command processing."""

    verification: VerificationRecord


class TrackVerificationResponse(BaseModel):
    """Response for confirmation tracking updates."""

    verification: VerificationRecord
    maintenance_verified_event: MaintenanceVerifiedBlockchainEvent | None = None


class VerificationListResponse(BaseModel):
    """Collection response for verification records."""

    items: list[VerificationRecord]


class SepoliaConnectionResponse(BaseModel):
    """Connection status for Sepolia RPC and optional contract lookup."""

    connected: bool
    network: Literal["sepolia"] = "sepolia"
    expected_chain_id: int = Field(ge=1)
    chain_id: int | None = Field(default=None, ge=1)
    latest_block: int | None = Field(default=None, ge=0)
    contract_address: str | None = Field(default=None, pattern=r"^0x[a-fA-F0-9]{40}$")
    contract_deployed: bool | None = None
    checked_at: datetime
    message: str = Field(min_length=1, max_length=500)


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
