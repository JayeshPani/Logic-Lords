"""Compatibility entrypoint for fuzzy inference service."""

try:
    from .fuzzy_inference.main import app
except ImportError:  # pragma: no cover
    from fuzzy_inference.main import app

__all__ = ["app"]
