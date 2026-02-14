"""HTTP routes for report generation service."""

from datetime import datetime, timezone
import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import ReportGenerationEngine
from .observability import get_metrics, log_event
from .schemas import (
    GenerateReportRequest,
    GenerateReportResponse,
    HealthResponse,
    IngestEventResponse,
    InspectionRequestedEvent,
    MaintenanceCompletedEvent,
)
from .store import InMemoryReportContextStore

router = APIRouter()
logger = logging.getLogger("report_generation")

_settings = get_settings()
_store = InMemoryReportContextStore()
_metrics = get_metrics()
_engine = ReportGenerationEngine(settings=_settings, store=_store)


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


@router.post("/events/inspection-requested", response_model=IngestEventResponse)
def ingest_inspection_requested(payload: InspectionRequestedEvent) -> IngestEventResponse:
    _engine.ingest_inspection_context(payload)
    if _settings.metrics_enabled:
        _metrics.record_inspection_context()
    log_event(
        logger,
        "report_context_ingested_inspection",
        asset_id=payload.data.asset_id,
        ticket_id=payload.data.ticket_id,
        trace_id=payload.trace_id,
    )
    return IngestEventResponse()


@router.post("/events/maintenance-completed", response_model=IngestEventResponse)
def ingest_maintenance_completed(payload: MaintenanceCompletedEvent) -> IngestEventResponse:
    _engine.ingest_maintenance_context(payload)
    if _settings.metrics_enabled:
        _metrics.record_maintenance_context()
    log_event(
        logger,
        "report_context_ingested_maintenance",
        asset_id=payload.data.asset_id,
        maintenance_id=payload.data.maintenance_id,
        trace_id=payload.trace_id,
    )
    return IngestEventResponse()


@router.post("/generate", response_model=GenerateReportResponse, response_model_exclude_none=True)
def generate(payload: GenerateReportRequest) -> GenerateReportResponse:
    started = perf_counter()
    if _settings.metrics_enabled:
        _metrics.record_generate_request()

    log_event(
        logger,
        "report_generate_requested",
        maintenance_id=payload.command.payload.maintenance_id,
        asset_id=payload.command.payload.asset_id,
        report_type=payload.command.payload.report_type,
        trace_id=payload.command.trace_id,
    )

    try:
        response = _engine.generate(payload)
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_generate_success(latency_ms)
        log_event(
            logger,
            "report_generated",
            report_id=response.report_bundle.report_id,
            maintenance_id=response.report_bundle.maintenance_id,
            asset_id=response.report_bundle.asset_id,
            trace_id=payload.command.trace_id,
            evidence_hash=response.report_bundle.evidence_hash,
            latency_ms=round(latency_ms, 3),
        )
        return response
    except KeyError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_generate_error(latency_ms)
        detail = str(exc).strip("'")
        log_event(
            logger,
            "report_generate_missing_context",
            maintenance_id=payload.command.payload.maintenance_id,
            asset_id=payload.command.payload.asset_id,
            trace_id=payload.command.trace_id,
            error=detail,
            latency_ms=round(latency_ms, 3),
        )
        raise HTTPException(status_code=404, detail=detail) from exc
    except Exception as exc:  # pragma: no cover
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_generate_error(latency_ms)
        log_event(
            logger,
            "report_generate_error",
            maintenance_id=payload.command.payload.maintenance_id,
            asset_id=payload.command.payload.asset_id,
            trace_id=payload.command.trace_id,
            error=str(exc),
            latency_ms=round(latency_ms, 3),
        )
        raise
