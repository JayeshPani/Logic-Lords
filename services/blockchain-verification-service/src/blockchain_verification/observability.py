"""Structured logging and in-memory metrics for blockchain verification service."""

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


class VerificationMetrics:
    """Thread-safe in-memory metrics for verification lifecycle."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.record_requests_total = 0
            self.track_requests_total = 0
            self.submitted_total = 0
            self.confirmed_total = 0
            self.failed_total = 0
            self.record_latency_ms_sum = 0.0
            self.record_latency_ms_count = 0
            self.track_latency_ms_sum = 0.0
            self.track_latency_ms_count = 0

    def record_record_request(self, latency_ms: float) -> None:
        with self._lock:
            self.record_requests_total += 1
            self.record_latency_ms_sum += max(latency_ms, 0.0)
            self.record_latency_ms_count += 1

    def record_track_request(self, latency_ms: float) -> None:
        with self._lock:
            self.track_requests_total += 1
            self.track_latency_ms_sum += max(latency_ms, 0.0)
            self.track_latency_ms_count += 1

    def record_submitted(self) -> None:
        with self._lock:
            self.submitted_total += 1

    def record_confirmed(self) -> None:
        with self._lock:
            self.confirmed_total += 1

    def record_failed(self) -> None:
        with self._lock:
            self.failed_total += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_verification_record_requests_total Total record requests.",
                "# TYPE infraguard_verification_record_requests_total counter",
                f"infraguard_verification_record_requests_total {self.record_requests_total}",
                "# HELP infraguard_verification_track_requests_total Total track requests.",
                "# TYPE infraguard_verification_track_requests_total counter",
                f"infraguard_verification_track_requests_total {self.track_requests_total}",
                "# HELP infraguard_verification_submitted_total Total submitted verifications.",
                "# TYPE infraguard_verification_submitted_total counter",
                f"infraguard_verification_submitted_total {self.submitted_total}",
                "# HELP infraguard_verification_confirmed_total Total confirmed verifications.",
                "# TYPE infraguard_verification_confirmed_total counter",
                f"infraguard_verification_confirmed_total {self.confirmed_total}",
                "# HELP infraguard_verification_failed_total Total failed verifications.",
                "# TYPE infraguard_verification_failed_total counter",
                f"infraguard_verification_failed_total {self.failed_total}",
                "# HELP infraguard_verification_record_latency_ms_sum Sum of record latency in milliseconds.",
                "# TYPE infraguard_verification_record_latency_ms_sum counter",
                f"infraguard_verification_record_latency_ms_sum {self.record_latency_ms_sum:.3f}",
                "# HELP infraguard_verification_record_latency_ms_count Number of record latency observations.",
                "# TYPE infraguard_verification_record_latency_ms_count counter",
                f"infraguard_verification_record_latency_ms_count {self.record_latency_ms_count}",
                "# HELP infraguard_verification_track_latency_ms_sum Sum of track latency in milliseconds.",
                "# TYPE infraguard_verification_track_latency_ms_sum counter",
                f"infraguard_verification_track_latency_ms_sum {self.track_latency_ms_sum:.3f}",
                "# HELP infraguard_verification_track_latency_ms_count Number of track latency observations.",
                "# TYPE infraguard_verification_track_latency_ms_count counter",
                f"infraguard_verification_track_latency_ms_count {self.track_latency_ms_count}",
            ]
        return "\n".join(lines) + "\n"


_metrics = VerificationMetrics()


def get_metrics() -> VerificationMetrics:
    """Return singleton metrics collector."""

    return _metrics
