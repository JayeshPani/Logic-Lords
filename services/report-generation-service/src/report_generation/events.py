"""Message builders for report-generation outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def build_report_generated_event(
    *,
    report_id: str,
    maintenance_id: str,
    asset_id: str,
    report_type: str,
    generated_at: datetime,
    evidence_hash: str,
    source_trace_ids: list[str],
    source_event_ids: list[str],
    trace_id: str,
    produced_by: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `report.generated` event envelope."""

    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": "report.generated",
        "event_version": "v1",
        "occurred_at": generated_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "report_id": report_id,
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "report_type": report_type,
            "generated_at": generated_at.isoformat(),
            "evidence_hash": evidence_hash,
            "source_trace_ids": source_trace_ids,
            "source_event_ids": source_event_ids,
        },
    }
    if correlation_id:
        event["correlation_id"] = correlation_id
    return event


def build_verification_record_command(
    *,
    maintenance_id: str,
    asset_id: str,
    evidence_hash: str,
    network: str,
    contract_address: str,
    chain_id: int,
    trace_id: str,
    requested_by: str,
    requested_at: datetime,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `verification.record.blockchain` command envelope."""

    command: dict[str, Any] = {
        "command_id": str(uuid4()),
        "command_type": "verification.record.blockchain",
        "command_version": "v1",
        "requested_at": requested_at.isoformat(),
        "requested_by": requested_by,
        "trace_id": trace_id,
        "payload": {
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "evidence_hash": evidence_hash,
            "network": network,
            "contract_address": contract_address,
            "chain_id": chain_id,
        },
    }
    if correlation_id:
        command["correlation_id"] = correlation_id
    return command
