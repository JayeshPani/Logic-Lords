"""Structured logging and in-memory metrics for notification service."""

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


class NotificationMetrics:
    """Thread-safe in-memory metrics for dispatch runtime."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.dispatch_requests_total = 0
            self.dispatch_delivered_total = 0
            self.dispatch_failed_total = 0
            self.retries_total = 0
            self.fallback_switches_total = 0
            self.dispatch_latency_ms_sum = 0.0
            self.dispatch_latency_ms_count = 0

    def record_dispatch_request(self) -> None:
        with self._lock:
            self.dispatch_requests_total += 1

    def record_delivered(self, latency_ms: float) -> None:
        with self._lock:
            self.dispatch_delivered_total += 1
            self.dispatch_latency_ms_sum += max(latency_ms, 0.0)
            self.dispatch_latency_ms_count += 1

    def record_failed(self, latency_ms: float) -> None:
        with self._lock:
            self.dispatch_failed_total += 1
            self.dispatch_latency_ms_sum += max(latency_ms, 0.0)
            self.dispatch_latency_ms_count += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retries_total += 1

    def record_fallback_switch(self) -> None:
        with self._lock:
            self.fallback_switches_total += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_notification_dispatch_requests_total Total dispatch requests received.",
                "# TYPE infraguard_notification_dispatch_requests_total counter",
                f"infraguard_notification_dispatch_requests_total {self.dispatch_requests_total}",
                "# HELP infraguard_notification_dispatch_delivered_total Total delivered notifications.",
                "# TYPE infraguard_notification_dispatch_delivered_total counter",
                f"infraguard_notification_dispatch_delivered_total {self.dispatch_delivered_total}",
                "# HELP infraguard_notification_dispatch_failed_total Total failed notifications.",
                "# TYPE infraguard_notification_dispatch_failed_total counter",
                f"infraguard_notification_dispatch_failed_total {self.dispatch_failed_total}",
                "# HELP infraguard_notification_retries_total Total retry attempts across channels.",
                "# TYPE infraguard_notification_retries_total counter",
                f"infraguard_notification_retries_total {self.retries_total}",
                "# HELP infraguard_notification_fallback_switches_total Total fallback channel switches.",
                "# TYPE infraguard_notification_fallback_switches_total counter",
                f"infraguard_notification_fallback_switches_total {self.fallback_switches_total}",
                "# HELP infraguard_notification_dispatch_latency_ms_sum Sum of dispatch latency in milliseconds.",
                "# TYPE infraguard_notification_dispatch_latency_ms_sum counter",
                f"infraguard_notification_dispatch_latency_ms_sum {self.dispatch_latency_ms_sum:.3f}",
                "# HELP infraguard_notification_dispatch_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_notification_dispatch_latency_ms_count counter",
                f"infraguard_notification_dispatch_latency_ms_count {self.dispatch_latency_ms_count}",
            ]
        return "\n".join(lines) + "\n"


_metrics = NotificationMetrics()


def get_metrics() -> NotificationMetrics:
    """Return singleton metrics collector."""

    return _metrics
