"""Structured logging and in-memory metrics for anomaly detection service."""

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


class AnomalyMetrics:
    """Thread-safe in-memory metrics for /detect calls."""

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
            self.last_anomaly_score = 0.0

    def record_request(self) -> None:
        with self._lock:
            self.requests_total += 1

    def record_success(self, latency_ms: float, anomaly_score: float) -> None:
        with self._lock:
            self.success_total += 1
            self.latency_ms_sum += max(latency_ms, 0.0)
            self.latency_ms_count += 1
            self.last_anomaly_score = max(0.0, min(1.0, anomaly_score))

    def record_error(self, latency_ms: float) -> None:
        with self._lock:
            self.errors_total += 1
            self.latency_ms_sum += max(latency_ms, 0.0)
            self.latency_ms_count += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_anomaly_requests_total Total anomaly-detect requests received.",
                "# TYPE infraguard_anomaly_requests_total counter",
                f"infraguard_anomaly_requests_total {self.requests_total}",
                "# HELP infraguard_anomaly_success_total Total successful anomaly-detect responses.",
                "# TYPE infraguard_anomaly_success_total counter",
                f"infraguard_anomaly_success_total {self.success_total}",
                "# HELP infraguard_anomaly_errors_total Total failed anomaly-detect requests.",
                "# TYPE infraguard_anomaly_errors_total counter",
                f"infraguard_anomaly_errors_total {self.errors_total}",
                "# HELP infraguard_anomaly_latency_ms_sum Sum of anomaly-detect latency in milliseconds.",
                "# TYPE infraguard_anomaly_latency_ms_sum counter",
                f"infraguard_anomaly_latency_ms_sum {self.latency_ms_sum:.3f}",
                "# HELP infraguard_anomaly_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_anomaly_latency_ms_count counter",
                f"infraguard_anomaly_latency_ms_count {self.latency_ms_count}",
                "# HELP infraguard_anomaly_last_score Last computed anomaly score.",
                "# TYPE infraguard_anomaly_last_score gauge",
                f"infraguard_anomaly_last_score {self.last_anomaly_score:.4f}",
            ]
        return "\n".join(lines) + "\n"


_metrics = AnomalyMetrics()


def get_metrics() -> AnomalyMetrics:
    """Return singleton metrics collector."""

    return _metrics
