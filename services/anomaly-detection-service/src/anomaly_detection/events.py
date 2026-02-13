"""Event payload builders for anomaly detection output."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from .engine import AnomalyResult


def build_asset_anomaly_detected_event(
    *,
    asset_id: str,
    evaluated_at: datetime,
    result: AnomalyResult,
    trace_id: str,
    produced_by: str,
) -> dict[str, Any]:
    """Build `asset.anomaly.detected` event envelope."""

    return {
        "event_id": str(uuid4()),
        "event_type": "asset.anomaly.detected",
        "event_version": "v1",
        "occurred_at": evaluated_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "asset_id": asset_id,
            "evaluated_at": evaluated_at.isoformat(),
            "anomaly_score": result.anomaly_score,
            "anomaly_flag": result.anomaly_flag,
            "detector_mode": result.detector_mode,
        },
    }
