"""Structured logging and in-memory metrics for forecast service."""

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


class ForecastMetrics:
    """Thread-safe in-memory metrics for /forecast calls."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests_total = 0
            self.success_total = 0
            self.errors_total = 0
            self.latency_ms_sum = 0.0
            self.latency_ms_count = 0
            self.last_failure_probability = 0.0

    def record_request(self) -> None:
        with self._lock:
            self.requests_total += 1

    def record_success(self, latency_ms: float, failure_probability: float) -> None:
        with self._lock:
            self.success_total += 1
            self.latency_ms_sum += max(latency_ms, 0.0)
            self.latency_ms_count += 1
            self.last_failure_probability = max(0.0, min(1.0, failure_probability))

    def record_error(self, latency_ms: float) -> None:
        with self._lock:
            self.errors_total += 1
            self.latency_ms_sum += max(latency_ms, 0.0)
            self.latency_ms_count += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_forecast_requests_total Total forecast requests received.",
                "# TYPE infraguard_forecast_requests_total counter",
                f"infraguard_forecast_requests_total {self.requests_total}",
                "# HELP infraguard_forecast_success_total Total successful forecast responses.",
                "# TYPE infraguard_forecast_success_total counter",
                f"infraguard_forecast_success_total {self.success_total}",
                "# HELP infraguard_forecast_errors_total Total failed forecast requests.",
                "# TYPE infraguard_forecast_errors_total counter",
                f"infraguard_forecast_errors_total {self.errors_total}",
                "# HELP infraguard_forecast_latency_ms_sum Sum of forecast request latency in milliseconds.",
                "# TYPE infraguard_forecast_latency_ms_sum counter",
                f"infraguard_forecast_latency_ms_sum {self.latency_ms_sum:.3f}",
                "# HELP infraguard_forecast_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_forecast_latency_ms_count counter",
                f"infraguard_forecast_latency_ms_count {self.latency_ms_count}",
                "# HELP infraguard_forecast_last_failure_probability Last computed failure probability.",
                "# TYPE infraguard_forecast_last_failure_probability gauge",
                f"infraguard_forecast_last_failure_probability {self.last_failure_probability:.4f}",
            ]
        return "\n".join(lines) + "\n"


_metrics = ForecastMetrics()


def get_metrics() -> ForecastMetrics:
    """Return singleton metrics collector."""

    return _metrics
