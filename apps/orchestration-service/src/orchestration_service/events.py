"""Event and command payload builders for orchestration workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def build_inspection_create_command(
    *,
    asset_id: str,
    priority: str,
    reason: str,
    triggered_by_event_id: str,
    trace_id: str,
    requested_by: str,
    requested_at: datetime,
    health_score: float | None = None,
    failure_probability: float | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `inspection.create` command envelope."""

    payload: dict[str, Any] = {
        "asset_id": asset_id,
        "priority": priority,
        "reason": reason,
        "triggered_by_event_id": triggered_by_event_id,
    }
    if health_score is not None:
        payload["health_score"] = max(0.0, min(1.0, health_score))
    if failure_probability is not None:
        payload["failure_probability"] = max(0.0, min(1.0, failure_probability))

    command: dict[str, Any] = {
        "command_id": str(uuid4()),
        "command_type": "inspection.create",
        "command_version": "v1",
        "requested_at": requested_at.isoformat(),
        "requested_by": requested_by,
        "trace_id": trace_id,
        "payload": payload,
    }
    if correlation_id:
        command["correlation_id"] = correlation_id
    return command


def build_inspection_requested_event(
    *,
    ticket_id: str,
    asset_id: str,
    requested_at: datetime,
    priority: str,
    reason: str,
    trace_id: str,
    produced_by: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `inspection.requested` event envelope."""

    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": "inspection.requested",
        "event_version": "v1",
        "occurred_at": requested_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "ticket_id": ticket_id,
            "asset_id": asset_id,
            "requested_at": requested_at.isoformat(),
            "priority": priority,
            "reason": reason,
        },
    }
    if correlation_id:
        event["correlation_id"] = correlation_id
    return event


def build_maintenance_completed_event(
    *,
    maintenance_id: str,
    asset_id: str,
    completed_at: datetime,
    performed_by: str,
    summary: str | None,
    trace_id: str,
    produced_by: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `maintenance.completed` event envelope."""

    data: dict[str, Any] = {
        "maintenance_id": maintenance_id,
        "asset_id": asset_id,
        "completed_at": completed_at.isoformat(),
        "performed_by": performed_by,
    }
    if summary:
        data["summary"] = summary

    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": "maintenance.completed",
        "event_version": "v1",
        "occurred_at": completed_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": data,
    }
    if correlation_id:
        event["correlation_id"] = correlation_id
    return event


def build_notification_dispatch_command(
    *,
    channel: str,
    fallback_channels: list[str] | None,
    recipient: str,
    message: str,
    severity: str,
    context: dict[str, Any] | None,
    trace_id: str,
    requested_by: str,
    requested_at: datetime,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `notification.dispatch` command envelope."""

    payload: dict[str, Any] = {
        "channel": channel,
        "recipient": recipient,
        "message": message,
        "severity": severity,
    }
    if fallback_channels:
        payload["fallback_channels"] = fallback_channels
    if context:
        payload["context"] = context

    command: dict[str, Any] = {
        "command_id": str(uuid4()),
        "command_type": "notification.dispatch",
        "command_version": "v1",
        "requested_at": requested_at.isoformat(),
        "requested_by": requested_by,
        "trace_id": trace_id,
        "payload": payload,
    }
    if correlation_id:
        command["correlation_id"] = correlation_id
    return command


def build_report_generate_request(
    *,
    maintenance_id: str,
    asset_id: str,
    trace_id: str,
    requested_by: str,
    requested_at: datetime,
    correlation_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build payload for report-generation `/generate` endpoint."""

    command: dict[str, Any] = {
        "command_id": str(uuid4()),
        "command_type": "report.generate",
        "command_version": "v1",
        "requested_at": requested_at.isoformat(),
        "requested_by": requested_by,
        "trace_id": trace_id,
        "payload": {
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "report_type": "maintenance_verification",
        },
    }
    if correlation_id:
        command["correlation_id"] = correlation_id

    request_payload: dict[str, Any] = {"command": command}
    if generated_at is not None:
        request_payload["generated_at"] = generated_at.isoformat()
    return request_payload
