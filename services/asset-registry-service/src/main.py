"""Compatibility entrypoint for existing service path."""

try:
    from .asset_registry.main import app
except ImportError:  # pragma: no cover
    from asset_registry.main import app

__all__ = ["app"]
