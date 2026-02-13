"""HTTP routes for blockchain verification service."""

from datetime import datetime, timezone
import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import BlockchainVerificationEngine
from .observability import get_metrics, log_event
from .schemas import (
    HealthResponse,
    MaintenanceVerifiedBlockchainEvent,
    RecordVerificationResponse,
    TrackVerificationResponse,
    VerificationListResponse,
    VerificationRecord,
    VerificationRecordBlockchainCommand,
)
from .store import InMemoryVerificationStore, VerificationRecordMutable

router = APIRouter()
logger = logging.getLogger("blockchain_verification")

_settings = get_settings()
_store = InMemoryVerificationStore()
_metrics = get_metrics()
_engine = BlockchainVerificationEngine(settings=_settings, store=_store)


def _to_record(record: VerificationRecordMutable) -> VerificationRecord:
    return VerificationRecord(
        verification_id=record.verification_id,
        command_id=record.command_id,
        maintenance_id=record.maintenance_id,
        asset_id=record.asset_id,
        verification_status=record.verification_status,
        evidence_hash=record.evidence_hash,
        tx_hash=record.tx_hash,
        network=record.network,
        contract_address=record.contract_address,
        chain_id=record.chain_id,
        block_number=record.block_number,
        confirmations=record.confirmations,
        required_confirmations=record.required_confirmations,
        submitted_at=record.submitted_at,
        confirmed_at=record.confirmed_at,
        failure_reason=record.failure_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        trace_id=record.trace_id,
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


@router.post("/record", response_model=RecordVerificationResponse, response_model_exclude_none=True)
def record(payload: VerificationRecordBlockchainCommand) -> RecordVerificationResponse:
    started = perf_counter()

    log_event(
        logger,
        "verification_record_requested",
        maintenance_id=payload.payload.maintenance_id,
        asset_id=payload.payload.asset_id,
        trace_id=payload.trace_id,
        network=payload.payload.network,
        chain_id=payload.payload.chain_id,
    )

    try:
        record_obj = _engine.record(payload)
    except ValueError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_record_request(latency_ms)
            _metrics.record_failed()
        log_event(
            logger,
            "verification_record_conflict",
            maintenance_id=payload.payload.maintenance_id,
            trace_id=payload.trace_id,
            error=str(exc),
            latency_ms=round(latency_ms, 3),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    latency_ms = (perf_counter() - started) * 1000.0
    if _settings.metrics_enabled:
        _metrics.record_record_request(latency_ms)
        _metrics.record_submitted()

    log_event(
        logger,
        "verification_record_submitted",
        verification_id=record_obj.verification_id,
        maintenance_id=record_obj.maintenance_id,
        trace_id=record_obj.trace_id,
        tx_hash=record_obj.tx_hash,
        block_number=record_obj.block_number,
        latency_ms=round(latency_ms, 3),
    )

    return RecordVerificationResponse(verification=_to_record(record_obj))


@router.post(
    "/verifications/{maintenance_id}/track",
    response_model=TrackVerificationResponse,
    response_model_exclude_none=True,
)
def track(maintenance_id: str) -> TrackVerificationResponse:
    started = perf_counter()

    try:
        result = _engine.track(maintenance_id)
    except KeyError as exc:
        latency_ms = (perf_counter() - started) * 1000.0
        if _settings.metrics_enabled:
            _metrics.record_track_request(latency_ms)
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc

    latency_ms = (perf_counter() - started) * 1000.0
    if _settings.metrics_enabled:
        _metrics.record_track_request(latency_ms)
        if result.maintenance_verified_event is not None:
            _metrics.record_confirmed()

    event_model = None
    if result.maintenance_verified_event is not None:
        event_model = MaintenanceVerifiedBlockchainEvent.model_validate(result.maintenance_verified_event)

    log_event(
        logger,
        "verification_track_result",
        maintenance_id=result.record.maintenance_id,
        verification_id=result.record.verification_id,
        trace_id=result.record.trace_id,
        status=result.record.verification_status,
        confirmations=result.record.confirmations,
        required_confirmations=result.record.required_confirmations,
        latency_ms=round(latency_ms, 3),
    )

    return TrackVerificationResponse(
        verification=_to_record(result.record),
        maintenance_verified_event=event_model,
    )


@router.get("/verifications/{maintenance_id}", response_model=VerificationRecord, response_model_exclude_none=True)
def get_verification(maintenance_id: str) -> VerificationRecord:
    record_obj = _engine.get(maintenance_id)
    if record_obj is None:
        raise HTTPException(status_code=404, detail="verification not found")
    return _to_record(record_obj)


@router.get("/verifications", response_model=VerificationListResponse, response_model_exclude_none=True)
def list_verifications(
    status: str | None = Query(default=None),
    asset_id: str | None = Query(default=None),
) -> VerificationListResponse:
    items = [_to_record(record_obj) for record_obj in _engine.list(status=status, asset_id=asset_id)]
    return VerificationListResponse(items=items)
