"""Compatibility entrypoint for notification service."""

try:
    from .notification_service.main import app
except ImportError:  # pragma: no cover
    from notification_service.main import app

__all__ = ["app"]
