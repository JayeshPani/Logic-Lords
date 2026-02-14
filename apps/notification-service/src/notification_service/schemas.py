"""Pydantic schemas for notification service APIs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


Channel = Literal["email", "sms", "webhook", "chat"]
Severity = Literal["healthy", "watch", "warning", "critical"]
DispatchStatus = Literal["delivered", "failed"]


class NotificationDispatchPayload(BaseModel):
    """Payload for `notification.dispatch` command."""

    channel: Channel
    fallback_channels: list[Channel] | None = None
    recipient: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=2000)
    severity: Severity
    context: dict[str, str | int | float | bool | None] | None = None


class NotificationDispatchCommand(BaseModel):
    """`notification.dispatch` command envelope."""

    command_id: UUID
    command_type: Literal["notification.dispatch"]
    command_version: str = Field(pattern=r"^v[0-9]+$")
    requested_at: datetime
    requested_by: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, str | int | float | bool | None] | None = None
    payload: NotificationDispatchPayload


class DispatchAttemptDetail(BaseModel):
    """One channel attempt entry for auditability."""

    channel: Channel
    attempt: int = Field(ge=1)
    succeeded: bool
    attempted_at: datetime
    error: str | None = None


class DispatchRecord(BaseModel):
    """Persistent dispatch state returned by APIs."""

    dispatch_id: str = Field(min_length=1)
    command_id: UUID
    status: DispatchStatus
    primary_channel: Channel
    final_channel: Channel
    recipient: str
    severity: Severity
    rendered_message: str
    channels_tried: list[Channel] = Field(min_length=1)
    attempts_total: int = Field(ge=1)
    retries_used: int = Field(ge=0)
    fallback_used: bool
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None
    attempt_log: list[DispatchAttemptDetail] = Field(min_length=1)


class NotificationDeliveryStatusData(BaseModel):
    """Payload for `notification.delivery.status` event data."""

    dispatch_id: str = Field(min_length=1)
    command_id: UUID
    status: DispatchStatus
    channel: Channel
    recipient: str = Field(min_length=1, max_length=256)
    severity: Severity
    attempts: int = Field(ge=1)
    retries_used: int = Field(ge=0)
    fallback_used: bool
    channels_tried: list[Channel] = Field(min_length=1)
    updated_at: datetime
    error: str | None = None


class NotificationDeliveryStatusEvent(BaseModel):
    """`notification.delivery.status` event envelope."""

    event_id: UUID
    event_type: Literal["notification.delivery.status"]
    event_version: str = Field(pattern=r"^v[0-9]+$")
    occurred_at: datetime
    produced_by: str = Field(min_length=1)
    trace_id: str = Field(min_length=8, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, str | int | float | bool | None] | None = None
    data: NotificationDeliveryStatusData


class DispatchResponse(BaseModel):
    """Response payload after dispatch attempt."""

    dispatch: DispatchRecord
    delivery_status_event: NotificationDeliveryStatusEvent


class DispatchListResponse(BaseModel):
    """Collection of dispatch records."""

    items: list[DispatchRecord]


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime
