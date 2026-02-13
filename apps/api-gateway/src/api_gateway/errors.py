"""API error primitives and response helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Structured API error used for consistent error envelopes."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        trace_id: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.trace_id = trace_id
        self.details = details


def build_meta() -> dict[str, str]:
    """Construct standard meta object for success responses."""

    return {
        "request_id": f"req_{uuid4().hex[:24]}",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    trace_id: str | None,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build standard error envelope response."""

    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id or f"trc_{uuid4().hex[:8]}",
        }
    }
    if details:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)
