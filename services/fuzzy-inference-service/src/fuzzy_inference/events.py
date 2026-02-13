"""Event payload builders for fuzzy inference outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def anomaly_flag_from_score(anomaly_score: float, threshold: float) -> int:
    """Convert anomaly score to binary flag."""

    return 1 if anomaly_score >= threshold else 0


def build_asset_risk_computed_event(
    *,
    asset_id: str,
    evaluated_at: datetime,
    health_score: float,
    risk_level: str,
    failure_probability_72h: float,
    anomaly_score: float,
    anomaly_threshold: float,
    trace_id: str,
    produced_by: str,
) -> dict[str, Any]:
    """Build `asset.risk.computed` event envelope."""

    return {
        "event_id": str(uuid4()),
        "event_type": "asset.risk.computed",
        "event_version": "v1",
        "occurred_at": evaluated_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "asset_id": asset_id,
            "evaluated_at": evaluated_at.isoformat(),
            "health_score": health_score,
            "risk_level": risk_level,
            "failure_probability_72h": failure_probability_72h,
            "anomaly_flag": anomaly_flag_from_score(anomaly_score, anomaly_threshold),
        },
    }
