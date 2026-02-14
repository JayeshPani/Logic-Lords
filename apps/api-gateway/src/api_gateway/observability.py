"""Structured logging and in-memory metrics for API gateway."""

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


class GatewayMetrics:
    """Thread-safe in-memory metrics for gateway requests."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests_total = 0
            self.errors_total = 0
            self.rate_limited_total = 0
            self.requests_by_path: dict[str, int] = {}

    def record_request(self, path: str) -> None:
        with self._lock:
            self.requests_total += 1
            self.requests_by_path[path] = self.requests_by_path.get(path, 0) + 1

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1

    def record_rate_limited(self) -> None:
        with self._lock:
            self.rate_limited_total += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP infraguard_api_gateway_requests_total Total gateway requests.",
                "# TYPE infraguard_api_gateway_requests_total counter",
                f"infraguard_api_gateway_requests_total {self.requests_total}",
                "# HELP infraguard_api_gateway_errors_total Total gateway errors.",
                "# TYPE infraguard_api_gateway_errors_total counter",
                f"infraguard_api_gateway_errors_total {self.errors_total}",
                "# HELP infraguard_api_gateway_rate_limited_total Total rate-limited requests.",
                "# TYPE infraguard_api_gateway_rate_limited_total counter",
                f"infraguard_api_gateway_rate_limited_total {self.rate_limited_total}",
            ]
            for path, count in sorted(self.requests_by_path.items()):
                safe_path = path.replace("/", "_").replace("-", "_").strip("_") or "root"
                lines.append(
                    f"infraguard_api_gateway_requests_path_total{{path=\"{safe_path}\"}} {count}"
                )
        return "\n".join(lines) + "\n"


_metrics = GatewayMetrics()


def get_metrics() -> GatewayMetrics:
    """Return singleton metrics collector."""

    return _metrics
