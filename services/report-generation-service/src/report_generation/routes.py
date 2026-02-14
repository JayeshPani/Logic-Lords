"""HTTP routes for report generation service."""

from datetime import datetime, timezone
import logging
import re
from time import perf_counter

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import ReportGenerationEngine
from .observability import get_metrics, log_event
from .schemas import (
    CreateEvidenceUploadRequest,
    CreateEvidenceUploadResponse,
    DeleteEvidenceResponse,
    EvidenceListResponse,
    FinalizeEvidenceUploadRequest,
    FinalizeEvidenceUploadResponse,
    GenerateReportRequest,
    GenerateReportResponse,
    HealthResponse,
    IngestEventResponse,
    InspectionRequestedEvent,
    MaintenanceCompletedEvent,
)
from .storage_adapter import (
    EvidenceObjectNotFound,
    EvidenceStorageError,
    EvidenceStorageUnavailable,
    FirebaseEvidenceStorageAdapter,
)
from .store import InMemoryReportContextStore

router = APIRouter()
logger = logging.getLogger("report_generation")

_settings = get_settings()
_store = InMemoryReportContextStore()
_metrics = get_metrics()
_engine = ReportGenerationEngine(settings=_settings, store=_store)
_storage_adapter = FirebaseEvidenceStorageAdapter(settings=_settings)


def _sanitize_filename(filename: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip())
    candidate = candidate.strip("._")
    return candidate or "evidence.bin"


def _storage_path(maintenance_id: str, evidence_id: str, filename: str) -> str:
    safe_name = _sanitize_filename(filename)
    return f"infraguard/evidence/{maintenance_id}/{evidence_id}/{safe_name}"


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


@router.post(
    "/maintenance/{maintenance_id}/evidence/uploads",
    response_model=CreateEvidenceUploadResponse,
    response_model_exclude_none=True,
)
def create_evidence_upload(
    maintenance_id: str,
    payload: CreateEvidenceUploadRequest,
) -> CreateEvidenceUploadResponse:
    maintenance = _store.get_maintenance(maintenance_id)
    if maintenance is None:
        raise HTTPException(status_code=404, detail=f"maintenance context not found: {maintenance_id}")

    if payload.asset_id != maintenance.data.asset_id:
        raise HTTPException(status_code=409, detail="asset_id does not match maintenance context.")

    if _store.is_evidence_locked(maintenance_id):
        raise HTTPException(status_code=409, detail="VERIFICATION_LOCKED")

    if payload.size_bytes > _settings.evidence_max_file_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"file too large; max allowed is {_settings.evidence_max_file_bytes} bytes.",
        )

    allowed_types = set(_settings.evidence_allowed_mime_types)
    if allowed_types and payload.content_type.lower() not in allowed_types:
        raise HTTPException(status_code=400, detail="unsupported content type for evidence upload.")

    now = datetime.now(tz=timezone.utc)
    evidence_id = _store.next_evidence_id(now)
    object_path = _storage_path(maintenance_id, evidence_id, payload.filename)

    try:
        session = _storage_adapter.create_upload_session(
            object_path=object_path,
            content_type=payload.content_type,
        )
    except EvidenceStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EvidenceStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        evidence = _store.create_evidence(
            evidence_id=evidence_id,
            maintenance_id=maintenance_id,
            asset_id=payload.asset_id,
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            storage_uri=session.storage_uri,
            storage_object_path=session.object_path,
            uploaded_by=payload.uploaded_by,
            uploaded_at=now,
            category=payload.category,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return CreateEvidenceUploadResponse(
        evidence=evidence,
        upload_url=session.upload_url,
        upload_method=session.upload_method,
        upload_headers=session.upload_headers,
        expires_at=session.expires_at,
    )


@router.post(
    "/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize",
    response_model=FinalizeEvidenceUploadResponse,
    response_model_exclude_none=True,
)
def finalize_evidence_upload(
    maintenance_id: str,
    evidence_id: str,
    payload: FinalizeEvidenceUploadRequest,
) -> FinalizeEvidenceUploadResponse:
    if _store.is_evidence_locked(maintenance_id):
        raise HTTPException(status_code=409, detail="VERIFICATION_LOCKED")

    stored = _store.get_evidence(maintenance_id, evidence_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="evidence record not found")

    object_path = _store.get_evidence_storage_object_path(maintenance_id, evidence_id)
    if not object_path:
        raise HTTPException(status_code=404, detail="evidence storage path not found")

    try:
        object_info = _storage_adapter.get_object_info(object_path=object_path)
        sha256_hex = _storage_adapter.compute_sha256(object_path=object_path)
    except EvidenceObjectNotFound as exc:
        raise HTTPException(status_code=409, detail=f"UPLOAD_NOT_FOUND: {exc}") from exc
    except EvidenceStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EvidenceStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if object_info.size_bytes > _settings.evidence_max_file_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"uploaded file exceeds max size {_settings.evidence_max_file_bytes} bytes.",
        )

    allowed_types = set(_settings.evidence_allowed_mime_types)
    if allowed_types and object_info.content_type and object_info.content_type.lower() not in allowed_types:
        raise HTTPException(status_code=400, detail="uploaded file content type is not allowed.")

    try:
        evidence = _store.finalize_evidence(
            maintenance_id=maintenance_id,
            evidence_id=evidence_id,
            sha256_hex=sha256_hex,
            size_bytes=object_info.size_bytes,
            content_type=object_info.content_type or stored.content_type,
            finalized_at=datetime.now(tz=timezone.utc),
            finalized_by=payload.uploaded_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return FinalizeEvidenceUploadResponse(evidence=evidence)


@router.get(
    "/maintenance/{maintenance_id}/evidence",
    response_model=EvidenceListResponse,
    response_model_exclude_none=True,
)
def list_evidence(maintenance_id: str) -> EvidenceListResponse:
    maintenance = _store.get_maintenance(maintenance_id)
    if maintenance is None:
        raise HTTPException(status_code=404, detail=f"maintenance context not found: {maintenance_id}")

    return EvidenceListResponse(items=_store.list_evidence(maintenance_id))


@router.post(
    "/maintenance/{maintenance_id}/evidence/{evidence_id}/delete",
    response_model=DeleteEvidenceResponse,
    response_model_exclude_none=True,
)
def delete_evidence(maintenance_id: str, evidence_id: str) -> DeleteEvidenceResponse:
    try:
        evidence = _store.delete_evidence(maintenance_id=maintenance_id, evidence_id=evidence_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return DeleteEvidenceResponse(evidence=evidence)


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
    except ValueError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_generate_error(latency_ms)
        detail = str(exc).strip()
        log_event(
            logger,
            "report_generate_validation_error",
            maintenance_id=payload.command.payload.maintenance_id,
            asset_id=payload.command.payload.asset_id,
            trace_id=payload.command.trace_id,
            error=detail,
            latency_ms=round(latency_ms, 3),
        )
        raise HTTPException(status_code=409, detail=detail) from exc
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
