"""Compatibility entrypoint for report generation service."""

try:
    from .report_generation.main import app
except ImportError:  # pragma: no cover
    from report_generation.main import app

__all__ = ["app"]
