"""Compatibility entrypoint for anomaly detection service."""

try:
    from .anomaly_detection.main import app
except ImportError:  # pragma: no cover
    from anomaly_detection.main import app

__all__ = ["app"]
