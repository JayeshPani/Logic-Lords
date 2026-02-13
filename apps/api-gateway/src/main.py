"""Compatibility entrypoint for API gateway service."""

try:
    from .api_gateway.main import app
except ImportError:  # pragma: no cover
    from api_gateway.main import app

__all__ = ["app"]
