"""Compatibility entrypoint for blockchain verification service."""

try:
    from .blockchain_verification.main import app
except ImportError:  # pragma: no cover
    from blockchain_verification.main import app

__all__ = ["app"]
