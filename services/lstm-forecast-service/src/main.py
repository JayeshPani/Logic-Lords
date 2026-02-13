"""Compatibility entrypoint for forecast service."""

try:
    from .lstm_forecast.main import app
except ImportError:  # pragma: no cover
    from lstm_forecast.main import app

__all__ = ["app"]
