"""HTTP routes for orchestration service."""

from datetime import datetime, timezone
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .config import get_settings
from .engine import OrchestrationEngine
from .observability import get_metrics, log_event
from .schemas import (
    AcknowledgementRequest,
    AcknowledgementResponse,
    AssetFailurePredictedEvent,
    AssetRiskComputedEvent,
    AutomationIncident,
    CompleteMaintenanceRequest,
    CompleteMaintenanceResponse,
    ForecastEventIngestResponse,
    HealthResponse,
    IncidentListResponse,
    RiskEventIngestResponse,
    VerificationStateResponse,
    VerificationSubmitRequest,
    VerificationSubmitResponse,
    WorkflowListResponse,
    WorkflowStateResponse,
    WorkflowVerificationSummary,
)
from .store import InMemoryOrchestrationStore, WorkflowRecord

router = APIRouter()
logger = logging.getLogger("orchestration")

_settings = get_settings()
_store = InMemoryOrchestrationStore()
_metrics = get_metrics()
_engine = OrchestrationEngine(settings=_settings, store=_store, metrics=_metrics)


def _workflow_response(workflow: WorkflowRecord) -> WorkflowStateResponse:
    return WorkflowStateResponse(
        workflow_id=workflow.workflow_id,
        asset_id=workflow.asset_id,
        workflow_name=workflow.workflow_name,
        status=workflow.status,
        priority=workflow.priority,
        trigger_reason=workflow.trigger_reason,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        attempts=workflow.attempts,
        max_attempts=workflow.max_attempts,
        trace_id=workflow.trace_id,
        trigger_event_id=workflow.trigger_event_id,
        last_error=workflow.last_error,
        inspection_ticket_id=workflow.inspection_ticket_id,
        maintenance_id=workflow.maintenance_id,
        verification_status=workflow.verification_status,
        verification_maintenance_id=workflow.verification_maintenance_id,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
        verification_updated_at=workflow.verification_updated_at,
        escalation_stage=workflow.escalation_stage,
        authority_notified_at=workflow.authority_notified_at,
        authority_ack_deadline_at=workflow.authority_ack_deadline_at,
        acknowledged_at=workflow.acknowledged_at,
        acknowledged_by=workflow.acknowledged_by,
        ack_notes=workflow.ack_notes,
        police_notified_at=workflow.police_notified_at,
        management_dispatch_ids=workflow.management_dispatch_ids,
        police_dispatch_ids=workflow.police_dispatch_ids,
        inspection_create_command=workflow.inspection_create_command,
        inspection_requested_event=workflow.inspection_requested_event,
        maintenance_completed_event=workflow.maintenance_completed_event,
    )


def _incident_response(workflow: WorkflowRecord) -> AutomationIncident:
    stage = workflow.escalation_stage or "management_notified"
    return AutomationIncident(
        workflow_id=workflow.workflow_id,
        asset_id=workflow.asset_id,
        risk_priority=workflow.priority,
        escalation_stage=stage,
        status=workflow.status,
        trigger_reason=workflow.trigger_reason,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        authority_notified_at=workflow.authority_notified_at,
        authority_ack_deadline_at=workflow.authority_ack_deadline_at,
        acknowledged_at=workflow.acknowledged_at,
        acknowledged_by=workflow.acknowledged_by,
        ack_notes=workflow.ack_notes,
        police_notified_at=workflow.police_notified_at,
        management_dispatch_ids=workflow.management_dispatch_ids,
        police_dispatch_ids=workflow.police_dispatch_ids,
        inspection_ticket_id=workflow.inspection_ticket_id,
        maintenance_id=workflow.maintenance_id,
        verification_status=workflow.verification_status,
        verification_maintenance_id=workflow.verification_maintenance_id,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
        verification_updated_at=workflow.verification_updated_at,
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


@router.post("/events/asset-failure-predicted", response_model=ForecastEventIngestResponse)
def ingest_asset_failure_predicted(payload: AssetFailurePredictedEvent, request: Request) -> ForecastEventIngestResponse:
    trace_id = request.headers.get("x-trace-id", "").strip() or payload.trace_id or uuid4().hex
    _engine.handle_forecast_event(payload)
    log_event(
        logger,
        "orchestration_forecast_event_ingested",
        asset_id=payload.data.asset_id,
        trace_id=trace_id,
        failure_probability_72h=payload.data.failure_probability_72h,
        confidence=payload.data.confidence,
    )
    return ForecastEventIngestResponse(asset_id=payload.data.asset_id)


@router.post(
    "/events/asset-risk-computed",
    response_model=RiskEventIngestResponse,
    response_model_exclude_none=True,
)
def ingest_asset_risk_computed(payload: AssetRiskComputedEvent, request: Request) -> RiskEventIngestResponse:
    trace_id = request.headers.get("x-trace-id", "").strip() or payload.trace_id or uuid4().hex

    log_event(
        logger,
        "orchestration_risk_event_received",
        asset_id=payload.data.asset_id,
        trace_id=trace_id,
        risk_level=payload.data.risk_level,
        health_score=payload.data.health_score,
        failure_probability_72h=payload.data.failure_probability_72h,
        anomaly_flag=payload.data.anomaly_flag,
    )

    decision = _engine.handle_risk_event(payload)
    workflow_status = decision.workflow.status if decision.workflow else None
    escalation_stage = decision.workflow.escalation_stage if decision.workflow else None

    log_event(
        logger,
        "orchestration_risk_event_decision",
        asset_id=payload.data.asset_id,
        trace_id=trace_id,
        workflow_triggered=decision.workflow_triggered,
        workflow_id=decision.workflow.workflow_id if decision.workflow else None,
        workflow_status=workflow_status,
        escalation_stage=escalation_stage,
        retries_used=decision.retries_used,
        reason=decision.reason,
    )

    return RiskEventIngestResponse(
        workflow_triggered=decision.workflow_triggered,
        workflow_id=decision.workflow.workflow_id if decision.workflow else None,
        workflow_status=workflow_status,
        escalation_stage=escalation_stage,
        reason=decision.reason,
        retries_used=decision.retries_used,
        inspection_create_command=decision.inspection_create_command,
        inspection_requested_event=decision.inspection_requested_event,
    )


@router.get("/workflows", response_model=WorkflowListResponse, response_model_exclude_none=True)
def list_workflows(
    asset_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> WorkflowListResponse:
    items = [_workflow_response(workflow) for workflow in _engine.list_workflows(asset_id=asset_id, status=status)]
    return WorkflowListResponse(items=items)


@router.get("/workflows/{workflow_id}", response_model=WorkflowStateResponse, response_model_exclude_none=True)
def get_workflow(workflow_id: str) -> WorkflowStateResponse:
    workflow = _engine.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _workflow_response(workflow)


@router.get("/incidents", response_model=IncidentListResponse, response_model_exclude_none=True)
def list_incidents(
    stage: str | None = Query(default=None),
    asset_id: str | None = Query(default=None),
) -> IncidentListResponse:
    workflows = _engine.list_incidents()
    if stage:
        workflows = [workflow for workflow in workflows if workflow.escalation_stage == stage]
    if asset_id:
        workflows = [workflow for workflow in workflows if workflow.asset_id == asset_id]
    items = [_incident_response(workflow) for workflow in workflows]
    return IncidentListResponse(items=items)


@router.get("/incidents/{workflow_id}", response_model=AutomationIncident, response_model_exclude_none=True)
def get_incident(workflow_id: str) -> AutomationIncident:
    workflow = _engine.get_workflow(workflow_id)
    if workflow is None or workflow.escalation_stage is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return _incident_response(workflow)


@router.post(
    "/incidents/{workflow_id}/acknowledge",
    response_model=AcknowledgementResponse,
    response_model_exclude_none=True,
)
def acknowledge_incident(
    workflow_id: str,
    payload: AcknowledgementRequest,
    request: Request,
) -> AcknowledgementResponse:
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex

    try:
        workflow = _engine.acknowledge_incident(
            workflow_id=workflow_id,
            acknowledged_by=payload.acknowledged_by,
            ack_notes=payload.ack_notes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="incident not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    acknowledged_at = workflow.acknowledged_at
    if acknowledged_at is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="acknowledgement not persisted")

    log_event(
        logger,
        "orchestration_ack_received",
        workflow_id=workflow_id,
        asset_id=workflow.asset_id,
        trace_id=trace_id,
        acknowledged_by=workflow.acknowledged_by,
        escalation_stage=workflow.escalation_stage,
    )

    return AcknowledgementResponse(
        workflow_id=workflow_id,
        escalation_stage=workflow.escalation_stage or "acknowledged",
        acknowledged_at=acknowledged_at,
        acknowledged_by=workflow.acknowledged_by or payload.acknowledged_by,
        ack_notes=workflow.ack_notes,
        police_notified_at=workflow.police_notified_at,
    )


@router.post(
    "/workflows/{workflow_id}/maintenance/completed",
    response_model=CompleteMaintenanceResponse,
    response_model_exclude_none=True,
)
def complete_maintenance(
    workflow_id: str,
    payload: CompleteMaintenanceRequest,
    request: Request,
) -> CompleteMaintenanceResponse:
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    try:
        workflow = _engine.complete_maintenance(
            workflow_id=workflow_id,
            performed_by=payload.performed_by,
            summary=payload.summary,
            operator_wallet_address=payload.operator_wallet_address,
            completed_at=payload.completed_at,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="workflow not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    event = workflow.maintenance_completed_event
    if event is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="maintenance event missing from workflow state")

    log_event(
        logger,
        "orchestration_maintenance_completed",
        workflow_id=workflow_id,
        asset_id=workflow.asset_id,
        trace_id=trace_id,
        maintenance_id=workflow.maintenance_id,
        performed_by=payload.performed_by,
        verification_status=workflow.verification_status,
        verification_maintenance_id=workflow.verification_maintenance_id,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
    )

    return CompleteMaintenanceResponse(
        workflow_id=workflow_id,
        workflow_status=workflow.status,
        maintenance_completed_event=event,
        verification_summary=(
            WorkflowVerificationSummary(
                verification_status=workflow.verification_status or "failed",
                verification_maintenance_id=workflow.verification_maintenance_id,
                verification_tx_hash=workflow.verification_tx_hash,
                verification_error=workflow.verification_error,
                verification_updated_at=workflow.verification_updated_at,
            )
            if workflow.verification_status is not None
            else None
        ),
    )


@router.post(
    "/maintenance/{maintenance_id}/verification/submit",
    response_model=VerificationSubmitResponse,
    response_model_exclude_none=True,
)
def submit_maintenance_verification(
    maintenance_id: str,
    payload: VerificationSubmitRequest,
    request: Request,
) -> VerificationSubmitResponse:
    trace_id = request.headers.get("x-trace-id", "").strip() or uuid4().hex
    try:
        workflow = _engine.submit_verification_by_maintenance_id(
            maintenance_id=maintenance_id,
            submitted_by=payload.submitted_by,
            operator_wallet_address=payload.operator_wallet_address,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="maintenance workflow not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    log_event(
        logger,
        "orchestration_verification_submitted",
        workflow_id=workflow.workflow_id,
        maintenance_id=maintenance_id,
        trace_id=trace_id,
        submitted_by=payload.submitted_by,
        verification_status=workflow.verification_status,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
    )

    return VerificationSubmitResponse(
        workflow_id=workflow.workflow_id,
        maintenance_id=maintenance_id,
        verification_status=workflow.verification_status or "failed",
        verification_maintenance_id=workflow.verification_maintenance_id,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
        verification_updated_at=workflow.verification_updated_at,
    )


@router.get(
    "/maintenance/{maintenance_id}/verification/state",
    response_model=VerificationStateResponse,
    response_model_exclude_none=True,
)
def get_maintenance_verification_state(maintenance_id: str) -> VerificationStateResponse:
    try:
        workflow = _engine.get_verification_state_by_maintenance_id(maintenance_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="maintenance workflow not found") from None

    return VerificationStateResponse(
        workflow_id=workflow.workflow_id,
        maintenance_id=maintenance_id,
        verification_status=workflow.verification_status or "failed",
        verification_maintenance_id=workflow.verification_maintenance_id,
        verification_tx_hash=workflow.verification_tx_hash,
        verification_error=workflow.verification_error,
        verification_updated_at=workflow.verification_updated_at,
    )
