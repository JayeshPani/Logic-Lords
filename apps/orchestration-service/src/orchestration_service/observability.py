"""Structured logging and in-memory metrics for orchestration service."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from threading import Lock
from typing import Any


def configure_logging(level: str) -> None:
    """Configure service logging format once."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
    )


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit one structured JSON log line."""

    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    logger.info(json.dumps(payload, default=str, separators=(",", ":")))


class OrchestrationMetrics:
    """Thread-safe in-memory metrics for orchestration runtime."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.risk_events_total = 0
            self.forecast_events_total = 0
            self.workflows_started_total = 0
            self.workflows_ignored_total = 0
            self.inspection_requested_total = 0
            self.maintenance_completed_total = 0
            self.retries_total = 0
            self.workflow_failures_total = 0
            self.decision_latency_ms_sum = 0.0
            self.decision_latency_ms_count = 0

    def record_risk_event(self) -> None:
        with self._lock:
            self.risk_events_total += 1

    def record_forecast_event(self) -> None:
        with self._lock:
            self.forecast_events_total += 1

    def record_workflow_started(self) -> None:
        with self._lock:
            self.workflows_started_total += 1

    def record_workflow_ignored(self) -> None:
        with self._lock:
            self.workflows_ignored_total += 1

    def record_inspection_requested(self) -> None:
        with self._lock:
            self.inspection_requested_total += 1

    def record_maintenance_completed(self) -> None:
        with self._lock:
            self.maintenance_completed_total += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retries_total += 1

    def record_workflow_failure(self) -> None:
        with self._lock:
            self.workflow_failures_total += 1

    def record_decision_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.decision_latency_ms_sum += max(latency_ms, 0.0)
            self.decision_latency_ms_count += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_orchestration_risk_events_total Total risk events received.",
                "# TYPE infraguard_orchestration_risk_events_total counter",
                f"infraguard_orchestration_risk_events_total {self.risk_events_total}",
                "# HELP infraguard_orchestration_forecast_events_total Total forecast events received.",
                "# TYPE infraguard_orchestration_forecast_events_total counter",
                f"infraguard_orchestration_forecast_events_total {self.forecast_events_total}",
                "# HELP infraguard_orchestration_workflows_started_total Workflows started for high-risk assets.",
                "# TYPE infraguard_orchestration_workflows_started_total counter",
                f"infraguard_orchestration_workflows_started_total {self.workflows_started_total}",
                "# HELP infraguard_orchestration_workflows_ignored_total Risk events that did not trigger workflows.",
                "# TYPE infraguard_orchestration_workflows_ignored_total counter",
                f"infraguard_orchestration_workflows_ignored_total {self.workflows_ignored_total}",
                "# HELP infraguard_orchestration_inspection_requested_total inspection.requested events produced.",
                "# TYPE infraguard_orchestration_inspection_requested_total counter",
                f"infraguard_orchestration_inspection_requested_total {self.inspection_requested_total}",
                "# HELP infraguard_orchestration_maintenance_completed_total maintenance.completed events produced.",
                "# TYPE infraguard_orchestration_maintenance_completed_total counter",
                f"infraguard_orchestration_maintenance_completed_total {self.maintenance_completed_total}",
                "# HELP infraguard_orchestration_retries_total Retry attempts used by workflow dispatch.",
                "# TYPE infraguard_orchestration_retries_total counter",
                f"infraguard_orchestration_retries_total {self.retries_total}",
                "# HELP infraguard_orchestration_workflow_failures_total Workflows that exhausted retries.",
                "# TYPE infraguard_orchestration_workflow_failures_total counter",
                f"infraguard_orchestration_workflow_failures_total {self.workflow_failures_total}",
                "# HELP infraguard_orchestration_decision_latency_ms_sum Sum of decision latency in milliseconds.",
                "# TYPE infraguard_orchestration_decision_latency_ms_sum counter",
                f"infraguard_orchestration_decision_latency_ms_sum {self.decision_latency_ms_sum:.3f}",
                "# HELP infraguard_orchestration_decision_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_orchestration_decision_latency_ms_count counter",
                f"infraguard_orchestration_decision_latency_ms_count {self.decision_latency_ms_count}",
            ]
        return "\n".join(lines) + "\n"


_metrics = OrchestrationMetrics()


def get_metrics() -> OrchestrationMetrics:
    """Return singleton metrics collector."""

    return _metrics
