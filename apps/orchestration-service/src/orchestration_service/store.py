"""In-memory state store for orchestration workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass
class ForecastSnapshot:
    """Latest failure forecast retained per asset."""

    asset_id: str
    event_id: str
    trace_id: str
    generated_at: datetime
    failure_probability_72h: float
    confidence: float


@dataclass
class WorkflowRecord:
    """Mutable workflow state object."""

    workflow_id: str
    asset_id: str
    workflow_name: str
    status: str
    priority: str
    trigger_reason: str
    created_at: datetime
    updated_at: datetime
    attempts: int
    max_attempts: int
    trace_id: str
    trigger_event_id: str
    last_error: str | None = None
    inspection_ticket_id: str | None = None
    maintenance_id: str | None = None
    escalation_stage: str | None = None
    authority_notified_at: datetime | None = None
    authority_ack_deadline_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    ack_notes: str | None = None
    police_notified_at: datetime | None = None
    management_dispatch_ids: list[str] = field(default_factory=list)
    police_dispatch_ids: list[str] = field(default_factory=list)
    verification_status: str | None = None
    verification_maintenance_id: str | None = None
    verification_tx_hash: str | None = None
    verification_error: str | None = None
    verification_updated_at: datetime | None = None
    inspection_create_command: dict[str, Any] | None = None
    inspection_requested_event: dict[str, Any] | None = None
    maintenance_completed_event: dict[str, Any] | None = None


class InMemoryOrchestrationStore:
    """Thread-safe in-memory store used by orchestration runtime."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._workflow_counter = 0
            self._ticket_counter = 0
            self._maintenance_counter = 0
            self._workflows: dict[str, WorkflowRecord] = {}
            self._forecasts: dict[str, ForecastSnapshot] = {}

    def set_forecast(self, snapshot: ForecastSnapshot) -> None:
        with self._lock:
            self._forecasts[snapshot.asset_id] = snapshot

    def get_forecast(self, asset_id: str) -> ForecastSnapshot | None:
        with self._lock:
            return self._forecasts.get(asset_id)

    def create_workflow(
        self,
        *,
        asset_id: str,
        workflow_name: str,
        priority: str,
        trigger_reason: str,
        max_attempts: int,
        trace_id: str,
        trigger_event_id: str,
        started_at: datetime,
    ) -> WorkflowRecord:
        with self._lock:
            self._workflow_counter += 1
            workflow_id = f"wf_{started_at.strftime('%Y%m%d_%H%M%S')}_{self._workflow_counter:04d}"
            workflow = WorkflowRecord(
                workflow_id=workflow_id,
                asset_id=asset_id,
                workflow_name=workflow_name,
                status="started",
                priority=priority,
                trigger_reason=trigger_reason,
                created_at=started_at,
                updated_at=started_at,
                attempts=0,
                max_attempts=max_attempts,
                trace_id=trace_id,
                trigger_event_id=trigger_event_id,
            )
            self._workflows[workflow_id] = workflow
            return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._lock:
            return self._workflows.get(workflow_id)

    def get_workflow_by_maintenance_id(self, maintenance_id: str) -> WorkflowRecord | None:
        with self._lock:
            for workflow in self._workflows.values():
                if workflow.maintenance_id == maintenance_id:
                    return workflow
        return None

    def list_workflows(self, *, asset_id: str | None = None, status: str | None = None) -> list[WorkflowRecord]:
        with self._lock:
            records = list(self._workflows.values())

        if asset_id:
            records = [record for record in records if record.asset_id == asset_id]
        if status:
            records = [record for record in records if record.status == status]

        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def record_attempt(self, workflow_id: str, *, attempts: int, last_error: str | None, updated_at: datetime) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.attempts = attempts
            workflow.last_error = last_error
            workflow.updated_at = updated_at

    def mark_inspection_requested(
        self,
        workflow_id: str,
        *,
        attempts: int,
        ticket_id: str,
        inspection_create_command: dict[str, Any],
        inspection_requested_event: dict[str, Any],
        updated_at: datetime,
    ) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.status = "inspection_requested"
            workflow.attempts = attempts
            workflow.last_error = None
            workflow.inspection_ticket_id = ticket_id
            workflow.inspection_create_command = inspection_create_command
            workflow.inspection_requested_event = inspection_requested_event
            workflow.updated_at = updated_at

    def mark_failed(self, workflow_id: str, *, attempts: int, error: str, updated_at: datetime) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.status = "failed"
            workflow.attempts = attempts
            workflow.last_error = error
            workflow.updated_at = updated_at

    def mark_management_notified(
        self,
        workflow_id: str,
        *,
        notified_at: datetime,
        ack_deadline_at: datetime,
        dispatch_ids: list[str],
        updated_at: datetime,
    ) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.escalation_stage = "management_notified"
            workflow.authority_notified_at = notified_at
            workflow.authority_ack_deadline_at = ack_deadline_at
            workflow.management_dispatch_ids = list(dispatch_ids)
            workflow.updated_at = updated_at

    def acknowledge(
        self,
        workflow_id: str,
        *,
        acknowledged_at: datetime,
        acknowledged_by: str,
        ack_notes: str | None,
    ) -> WorkflowRecord | None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return None

            if workflow.acknowledged_at is None:
                workflow.acknowledged_at = acknowledged_at
            if workflow.acknowledged_by is None:
                workflow.acknowledged_by = acknowledged_by
            if ack_notes and workflow.ack_notes is None:
                workflow.ack_notes = ack_notes

            if workflow.escalation_stage not in {"police_notified", "maintenance_completed"}:
                workflow.escalation_stage = "acknowledged"

            workflow.updated_at = acknowledged_at
            return workflow

    def mark_police_notified(
        self,
        workflow_id: str,
        *,
        notified_at: datetime,
        dispatch_ids: list[str],
        updated_at: datetime,
    ) -> bool:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return False
            if workflow.escalation_stage in {"police_notified", "maintenance_completed"}:
                return False

            workflow.escalation_stage = "police_notified"
            workflow.police_notified_at = notified_at
            workflow.police_dispatch_ids = list(dispatch_ids)
            workflow.updated_at = updated_at
            return True

    def list_ack_timeout_candidates(self, now: datetime) -> list[WorkflowRecord]:
        with self._lock:
            records = list(self._workflows.values())

        return [
            record
            for record in records
            if record.status == "inspection_requested"
            and record.escalation_stage == "management_notified"
            and record.authority_ack_deadline_at is not None
            and record.authority_ack_deadline_at <= now
            and record.acknowledged_at is None
            and record.police_notified_at is None
        ]

    def mark_maintenance_completed(
        self,
        workflow_id: str,
        *,
        maintenance_id: str,
        event: dict[str, Any],
        updated_at: datetime,
    ) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.status = "maintenance_completed"
            workflow.escalation_stage = "maintenance_completed"
            workflow.maintenance_id = maintenance_id
            workflow.maintenance_completed_event = event
            workflow.updated_at = updated_at

    def mark_verification_result(
        self,
        workflow_id: str,
        *,
        verification_status: str,
        verification_maintenance_id: str | None,
        verification_tx_hash: str | None,
        verification_error: str | None,
        updated_at: datetime,
    ) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                return
            workflow.verification_status = verification_status
            workflow.verification_maintenance_id = verification_maintenance_id
            workflow.verification_tx_hash = verification_tx_hash
            workflow.verification_error = verification_error
            workflow.verification_updated_at = updated_at
            workflow.updated_at = updated_at

    def next_ticket_id(self, now: datetime) -> str:
        with self._lock:
            self._ticket_counter += 1
            return f"insp_{now.strftime('%Y%m%d')}_{self._ticket_counter:04d}"

    def next_maintenance_id(self, now: datetime) -> str:
        with self._lock:
            self._maintenance_counter += 1
            return f"mnt_{now.strftime('%Y%m%d')}_{self._maintenance_counter:04d}"
