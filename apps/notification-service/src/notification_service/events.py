"""Event payload builders for notification dispatch outcomes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def build_notification_delivery_status_event(
    *,
    dispatch_id: str,
    command_id: str,
    status: str,
    channel: str,
    recipient: str,
    severity: str,
    attempts: int,
    retries_used: int,
    fallback_used: bool,
    channels_tried: list[str],
    updated_at: datetime,
    trace_id: str,
    produced_by: str,
    error: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `notification.delivery.status` event envelope."""

    data: dict[str, Any] = {
        "dispatch_id": dispatch_id,
        "command_id": command_id,
        "status": status,
        "channel": channel,
        "recipient": recipient,
        "severity": severity,
        "attempts": attempts,
        "retries_used": retries_used,
        "fallback_used": fallback_used,
        "channels_tried": channels_tried,
        "updated_at": updated_at.isoformat(),
    }
    if error:
        data["error"] = error

    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": "notification.delivery.status",
        "event_version": "v1",
        "occurred_at": updated_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": data,
    }
    if correlation_id:
        event["correlation_id"] = correlation_id

    return event
