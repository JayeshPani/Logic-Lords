"""Structured logging and in-memory metrics for fuzzy inference service."""

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
    """Emit a structured log event as one JSON line."""

    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    logger.info(json.dumps(payload, default=str, separators=(",", ":")))


class InferenceMetrics:
    """Thread-safe in-memory metrics for infer endpoint activity."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.infer_requests_total = 0
            self.infer_success_total = 0
            self.infer_errors_total = 0
            self.infer_latency_ms_sum = 0.0
            self.infer_latency_ms_count = 0
            self.last_risk_score = 0.0

    def record_request(self) -> None:
        with self._lock:
            self.infer_requests_total += 1

    def record_success(self, latency_ms: float, risk_score: float) -> None:
        with self._lock:
            self.infer_success_total += 1
            self.infer_latency_ms_sum += max(latency_ms, 0.0)
            self.infer_latency_ms_count += 1
            self.last_risk_score = max(0.0, min(1.0, risk_score))

    def record_error(self, latency_ms: float) -> None:
        with self._lock:
            self.infer_errors_total += 1
            self.infer_latency_ms_sum += max(latency_ms, 0.0)
            self.infer_latency_ms_count += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_fuzzy_infer_requests_total Total infer requests received.",
                "# TYPE infraguard_fuzzy_infer_requests_total counter",
                f"infraguard_fuzzy_infer_requests_total {self.infer_requests_total}",
                "# HELP infraguard_fuzzy_infer_success_total Total successful infer responses.",
                "# TYPE infraguard_fuzzy_infer_success_total counter",
                f"infraguard_fuzzy_infer_success_total {self.infer_success_total}",
                "# HELP infraguard_fuzzy_infer_errors_total Total failed infer requests.",
                "# TYPE infraguard_fuzzy_infer_errors_total counter",
                f"infraguard_fuzzy_infer_errors_total {self.infer_errors_total}",
                "# HELP infraguard_fuzzy_infer_latency_ms_sum Sum of infer request latency in milliseconds.",
                "# TYPE infraguard_fuzzy_infer_latency_ms_sum counter",
                f"infraguard_fuzzy_infer_latency_ms_sum {self.infer_latency_ms_sum:.3f}",
                "# HELP infraguard_fuzzy_infer_latency_ms_count Number of latency observations.",
                "# TYPE infraguard_fuzzy_infer_latency_ms_count counter",
                f"infraguard_fuzzy_infer_latency_ms_count {self.infer_latency_ms_count}",
                "# HELP infraguard_fuzzy_infer_last_risk_score Last computed risk score.",
                "# TYPE infraguard_fuzzy_infer_last_risk_score gauge",
                f"infraguard_fuzzy_infer_last_risk_score {self.last_risk_score:.4f}",
            ]
        return "\n".join(lines) + "\n"


_metrics = InferenceMetrics()


def get_metrics() -> InferenceMetrics:
    """Return singleton metrics collector."""

    return _metrics
