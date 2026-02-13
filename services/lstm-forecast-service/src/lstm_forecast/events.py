"""Event payload builders for forecast output."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from .predictor import PredictorResult


def build_asset_failure_predicted_event(
    *,
    asset_id: str,
    generated_at: datetime,
    horizon_hours: int,
    result: PredictorResult,
    trace_id: str,
    produced_by: str,
) -> dict[str, Any]:
    """Build `asset.failure.predicted` event envelope."""

    return {
        "event_id": str(uuid4()),
        "event_type": "asset.failure.predicted",
        "event_version": "v1",
        "occurred_at": generated_at.isoformat(),
        "produced_by": produced_by,
        "trace_id": trace_id,
        "data": {
            "asset_id": asset_id,
            "generated_at": generated_at.isoformat(),
            "horizon_hours": horizon_hours,
            "failure_probability_72h": result.failure_probability,
            "confidence": result.confidence,
        },
    }
