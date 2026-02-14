"""HTTP routes for notification service."""

from datetime import datetime, timezone
import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import NotificationEngine
from .observability import get_metrics, log_event
from .schemas import (
    DispatchListResponse,
    DispatchRecord,
    DispatchResponse,
    HealthResponse,
    NotificationDeliveryStatusEvent,
    NotificationDispatchCommand,
)
from .store import DispatchRecordMutable, InMemoryDispatchStore

router = APIRouter()
logger = logging.getLogger("notification")

_settings = get_settings()
_store = InMemoryDispatchStore()
_metrics = get_metrics()
_engine = NotificationEngine(settings=_settings, store=_store, metrics=_metrics)


def _to_dispatch_record(record: DispatchRecordMutable) -> DispatchRecord:
    return DispatchRecord(
        dispatch_id=record.dispatch_id,
        command_id=record.command_id,
        status=record.status,
        primary_channel=record.primary_channel,
        final_channel=record.final_channel,
        recipient=record.recipient,
        severity=record.severity,
        rendered_message=record.rendered_message,
        channels_tried=record.channels_tried,
        attempts_total=record.attempts_total,
        retries_used=record.retries_used,
        fallback_used=record.fallback_used,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_error=record.last_error,
        attempt_log=record.attempt_log,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service=_settings.service_name,
        version=_settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    if not _settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics endpoint disabled")
    return _metrics.render_prometheus()


@router.post("/dispatch", response_model=DispatchResponse, response_model_exclude_none=True)
def dispatch(payload: NotificationDispatchCommand) -> DispatchResponse:
    started = perf_counter()
    if _settings.metrics_enabled:
        _metrics.record_dispatch_request()

    log_event(
        logger,
        "notification_dispatch_requested",
        command_id=str(payload.command_id),
        trace_id=payload.trace_id,
        channel=payload.payload.channel,
        recipient=payload.payload.recipient,
        severity=payload.payload.severity,
    )

    decision = _engine.dispatch(payload)
    latency_ms = (perf_counter() - started) * 1000.0
    if _settings.metrics_enabled:
        if decision.record.status == "delivered":
            _metrics.record_delivered(latency_ms)
        else:
            _metrics.record_failed(latency_ms)

    event = NotificationDeliveryStatusEvent.model_validate(decision.record.delivery_status_event)

    log_event(
        logger,
        "notification_dispatch_result",
        dispatch_id=decision.record.dispatch_id,
        command_id=decision.record.command_id,
        trace_id=payload.trace_id,
        status=decision.record.status,
        final_channel=decision.record.final_channel,
        retries_used=decision.record.retries_used,
        fallback_used=decision.record.fallback_used,
        latency_ms=round(latency_ms, 3),
    )

    return DispatchResponse(
        dispatch=_to_dispatch_record(decision.record),
        delivery_status_event=event,
    )


@router.get("/dispatches/{dispatch_id}", response_model=DispatchRecord, response_model_exclude_none=True)
def get_dispatch(dispatch_id: str) -> DispatchRecord:
    record = _engine.get_dispatch(dispatch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="dispatch not found")
    return _to_dispatch_record(record)


@router.get("/dispatches", response_model=DispatchListResponse, response_model_exclude_none=True)
def list_dispatches(
    status: str | None = Query(default=None),
    recipient: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> DispatchListResponse:
    items = [
        _to_dispatch_record(record)
        for record in _engine.list_dispatches(
            status=status,
            recipient=recipient,
            channel=channel,
            severity=severity,
        )
    ]
    return DispatchListResponse(items=items)
