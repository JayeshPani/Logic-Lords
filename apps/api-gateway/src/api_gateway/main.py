"""FastAPI app for API gateway."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .errors import ApiError, error_response
from .observability import configure_logging, get_metrics
from .routes import router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.service_name, version=settings.service_version)
app.include_router(router)
_metrics = get_metrics()
_dashboard_root = Path(__file__).resolve().parents[3] / "dashboard-web"
_dashboard_index = _dashboard_root / "index.html"
_dashboard_static_dir = _dashboard_root / "src"

if _dashboard_static_dir.exists():
    app.mount(
        "/dashboard-static",
        StaticFiles(directory=str(_dashboard_static_dir)),
        name="dashboard-static",
    )


@app.get("/dashboard", include_in_schema=False)
async def dashboard() -> FileResponse:
    if not _dashboard_index.exists():
        raise HTTPException(status_code=404, detail="Dashboard web assets not found.")
    return FileResponse(_dashboard_index)


@app.get("/dashboard-config.js", include_in_schema=False)
async def dashboard_config_js() -> Response:
    """Serve runtime dashboard defaults (no rebuild required)."""

    payload = {
        "firebase": {
            "enabled": bool(settings.dashboard_firebase_enabled),
            "dbUrl": settings.dashboard_firebase_db_url.strip(),
            "basePath": settings.dashboard_firebase_base_path.strip()
            or "infraguard/telemetry",
        }
    }
    script = (
        "window.__INFRAGUARD_DASHBOARD_CONFIG__ = "
        + json.dumps(payload, separators=(",", ":"))
        + ";"
    )
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"cache-control": "no-store"},
    )


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    if settings.metrics_enabled:
        _metrics.record_error()
        if exc.status_code == 429:
            _metrics.record_rate_limited()
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        trace_id=exc.trace_id or request.headers.get("x-trace-id"),
        details=exc.details,
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    if settings.metrics_enabled:
        _metrics.record_error()
    status_to_code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        429: "RATE_LIMITED",
    }
    code = status_to_code.get(exc.status_code, "INTERNAL_SERVER_ERROR")
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        trace_id=request.headers.get("x-trace-id"),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    if settings.metrics_enabled:
        _metrics.record_error()
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", [])),
            "issue": err.get("msg", "invalid value"),
        }
        for err in exc.errors()
    ]
    return error_response(
        status_code=422,
        code="UNPROCESSABLE_ENTITY",
        message="Validation failed.",
        trace_id=request.headers.get("x-trace-id"),
        details=details,
    )
