"""FastAPI app for orchestration service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging

from fastapi import FastAPI

from .config import get_settings
from .observability import configure_logging, log_event
from .routes import _engine, router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("orchestration")

app = FastAPI(title=settings.service_name, version=settings.service_version)
app.include_router(router)


async def _escalation_checker() -> None:
    interval_seconds = max(settings.escalation_check_interval_seconds, 5)
    while True:
        escalated = _engine.process_ack_deadline_timeouts()
        for workflow in escalated:
            log_event(
                logger,
                "orchestration_police_notified",
                workflow_id=workflow.workflow_id,
                asset_id=workflow.asset_id,
                escalation_stage=workflow.escalation_stage,
                police_notified_at=(workflow.police_notified_at or datetime.now(tz=timezone.utc)).isoformat(),
                trace_id=workflow.trace_id,
            )
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def startup_event() -> None:
    app.state.escalation_checker_task = asyncio.create_task(_escalation_checker())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    task = getattr(app.state, "escalation_checker_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
