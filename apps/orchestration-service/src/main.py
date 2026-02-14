"""Compatibility entrypoint for orchestration service."""

try:
    from .orchestration_service.main import app
except ImportError:  # pragma: no cover
    from orchestration_service.main import app

__all__ = ["app"]
