"""Compatibility entrypoint for health score service."""

try:
    from .health_score.main import app
except ImportError:  # pragma: no cover
    from health_score.main import app

__all__ = ["app"]
