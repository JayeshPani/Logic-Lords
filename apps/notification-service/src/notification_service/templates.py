"""Template rendering utilities for notification messages."""

from __future__ import annotations

from .schemas import Severity


class _SafeMap(dict[str, object]):
    def __missing__(self, key: str) -> str:  # pragma: no cover
        return "{" + key + "}"


TEMPLATES: dict[Severity, str] = {
    "healthy": "[HEALTHY] {message}",
    "watch": "[WATCH] {message} | asset={asset_id}",
    "warning": "[WARNING] {message} | asset={asset_id} | risk={risk_level}",
    "critical": "[CRITICAL] {message} | asset={asset_id} | ticket={ticket_id} | risk={risk_level}",
}


def render_message(
    *,
    severity: Severity,
    message: str,
    context: dict[str, str | int | float | bool | None] | None,
) -> str:
    """Render channel-ready message using severity template and context values."""

    payload: dict[str, object] = {"message": message}
    if context:
        payload.update(context)
    template = TEMPLATES[severity]
    return template.format_map(_SafeMap(payload))[:2000]
