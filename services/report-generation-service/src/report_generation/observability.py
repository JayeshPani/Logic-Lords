"""Structured logging and in-memory metrics for report generation service."""

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


class ReportMetrics:
    """Thread-safe in-memory metrics collector."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.generate_requests_total = 0
            self.generate_success_total = 0
            self.generate_errors_total = 0
            self.generated_reports_total = 0
            self.inspection_context_events_total = 0
            self.maintenance_context_events_total = 0
            self.generate_latency_ms_sum = 0.0
            self.generate_latency_ms_count = 0

    def record_generate_request(self) -> None:
        with self._lock:
            self.generate_requests_total += 1

    def record_generate_success(self, latency_ms: float) -> None:
        with self._lock:
            self.generate_success_total += 1
            self.generated_reports_total += 1
            self.generate_latency_ms_sum += max(latency_ms, 0.0)
            self.generate_latency_ms_count += 1

    def record_generate_error(self, latency_ms: float) -> None:
        with self._lock:
            self.generate_errors_total += 1
            self.generate_latency_ms_sum += max(latency_ms, 0.0)
            self.generate_latency_ms_count += 1

    def record_inspection_context(self) -> None:
        with self._lock:
            self.inspection_context_events_total += 1

    def record_maintenance_context(self) -> None:
        with self._lock:
            self.maintenance_context_events_total += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_report_generation_requests_total Total report generation requests.",
                "# TYPE infraguard_report_generation_requests_total counter",
                f"infraguard_report_generation_requests_total {self.generate_requests_total}",
                "# HELP infraguard_report_generation_success_total Total successful report generations.",
                "# TYPE infraguard_report_generation_success_total counter",
                f"infraguard_report_generation_success_total {self.generate_success_total}",
                "# HELP infraguard_report_generation_errors_total Total failed report generations.",
                "# TYPE infraguard_report_generation_errors_total counter",
                f"infraguard_report_generation_errors_total {self.generate_errors_total}",
                "# HELP infraguard_report_generation_generated_reports_total Total generated report bundles.",
                "# TYPE infraguard_report_generation_generated_reports_total counter",
                f"infraguard_report_generation_generated_reports_total {self.generated_reports_total}",
                "# HELP infraguard_report_generation_inspection_context_events_total inspection.requested context ingested.",
                "# TYPE infraguard_report_generation_inspection_context_events_total counter",
                f"infraguard_report_generation_inspection_context_events_total {self.inspection_context_events_total}",
                "# HELP infraguard_report_generation_maintenance_context_events_total maintenance.completed context ingested.",
                "# TYPE infraguard_report_generation_maintenance_context_events_total counter",
                f"infraguard_report_generation_maintenance_context_events_total {self.maintenance_context_events_total}",
                "# HELP infraguard_report_generation_latency_ms_sum Sum of generation latency in milliseconds.",
                "# TYPE infraguard_report_generation_latency_ms_sum counter",
                f"infraguard_report_generation_latency_ms_sum {self.generate_latency_ms_sum:.3f}",
                "# HELP infraguard_report_generation_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_report_generation_latency_ms_count counter",
                f"infraguard_report_generation_latency_ms_count {self.generate_latency_ms_count}",
            ]
        return "\n".join(lines) + "\n"


_metrics = ReportMetrics()


def get_metrics() -> ReportMetrics:
    """Return singleton metrics collector."""

    return _metrics
