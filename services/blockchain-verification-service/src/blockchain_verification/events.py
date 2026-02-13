"""Event builders for blockchain verification lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def build_maintenance_verified_blockchain_event(
    *,
    maintenance_id: str,
    asset_id: str,
    evidence_hash: str,
    tx_hash: str,
    network: str,
    verified_at: datetime,
    trace_id: str,
    produced_by: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Build `maintenance.verified.blockchain` event envelope."""

    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": "maintenance.verified.blockchain",
        "event_version": "v1",
        "occurred_at": verified_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "maintenance_id": maintenance_id,
            "asset_id": asset_id,
            "evidence_hash": evidence_hash,
            "tx_hash": tx_hash,
            "network": network,
            "verified_at": verified_at.isoformat(),
        },
    }
    if correlation_id:
        event["correlation_id"] = correlation_id
    return event
