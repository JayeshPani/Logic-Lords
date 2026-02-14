"""Core orchestration workflow logic for high-risk automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from .config import Settings
from .events import (
    build_inspection_create_command,
    build_inspection_requested_event,
    build_maintenance_completed_event,
)
from .observability import OrchestrationMetrics
from .schemas import AssetFailurePredictedEvent, AssetRiskComputedEvent
from .store import ForecastSnapshot, InMemoryOrchestrationStore, WorkflowRecord


InspectionDispatcher = Callable[[dict[str, Any], int], tuple[bool, str | None]]


@dataclass(frozen=True)
class RiskDecision:
    """Outcome of handling one `asset.risk.computed` event."""

    workflow_triggered: bool
    workflow: WorkflowRecord | None
    reason: str
    retries_used: int
    inspection_create_command: dict[str, Any] | None
    inspection_requested_event: dict[str, Any] | None


class OrchestrationEngine:
    """Coordinates workflow creation, retries, and event generation."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: InMemoryOrchestrationStore,
        metrics: OrchestrationMetrics,
    ) -> None:
        self._settings = settings
        self._store = store
        self._metrics = metrics
        self._inspection_dispatcher: InspectionDispatcher = self._default_dispatcher

    def reset_state_for_tests(self) -> None:
        """Reset store and dispatcher for deterministic tests."""

        self._store.reset()
        self._inspection_dispatcher = self._default_dispatcher

    def set_inspection_dispatcher_for_tests(self, dispatcher: InspectionDispatcher) -> None:
        """Inject test dispatcher to exercise retry behavior."""

        self._inspection_dispatcher = dispatcher

    def handle_forecast_event(self, event: AssetFailurePredictedEvent) -> None:
        """Store latest forecast context for an asset."""

        snapshot = ForecastSnapshot(
            asset_id=event.data.asset_id,
            event_id=str(event.event_id),
            trace_id=event.trace_id,
            generated_at=event.data.generated_at,
            failure_probability_72h=event.data.failure_probability_72h,
            confidence=event.data.confidence,
        )
        self._store.set_forecast(snapshot)
        self._metrics.record_forecast_event()

    def handle_risk_event(self, event: AssetRiskComputedEvent) -> RiskDecision:
        """Start and progress orchestration workflow when thresholds are met."""

        started = perf_counter()
        self._metrics.record_risk_event()

        forecast = self._store.get_forecast(event.data.asset_id)
        forecast_probability = forecast.failure_probability_72h if forecast else 0.0
        effective_failure_probability = max(event.data.failure_probability_72h, forecast_probability)

        should_trigger, reason = self._should_trigger(
            risk_level=event.data.risk_level,
            health_score=event.data.health_score,
            failure_probability=effective_failure_probability,
            anomaly_flag=event.data.anomaly_flag,
            forecast_available=forecast is not None,
        )
        if not should_trigger:
            self._metrics.record_workflow_ignored()
            self._metrics.record_decision_latency((perf_counter() - started) * 1000.0)
            return RiskDecision(
                workflow_triggered=False,
                workflow=None,
                reason=reason,
                retries_used=0,
                inspection_create_command=None,
                inspection_requested_event=None,
            )

        now = datetime.now(tz=timezone.utc)
        priority = self._priority_for(event.data.risk_level, effective_failure_probability)
        workflow = self._store.create_workflow(
            asset_id=event.data.asset_id,
            workflow_name=self._settings.workflow_name,
            priority=priority,
            trigger_reason=reason,
            max_attempts=self._settings.max_retry_attempts,
            trace_id=event.trace_id,
            trigger_event_id=str(event.event_id),
            started_at=now,
        )
        self._metrics.record_workflow_started()

        retries_used = 0
        inspection_command: dict[str, Any] | None = None

        for attempt in range(1, self._settings.max_retry_attempts + 1):
            issued_at = datetime.now(tz=timezone.utc)
            inspection_command = build_inspection_create_command(
                asset_id=event.data.asset_id,
                priority=priority,
                reason=reason,
                triggered_by_event_id=str(event.event_id),
                trace_id=event.trace_id,
                requested_by=self._settings.command_requested_by,
                requested_at=issued_at,
                health_score=event.data.health_score,
                failure_probability=effective_failure_probability,
                correlation_id=workflow.workflow_id,
            )

            success, error = self._dispatch_inspection_command(inspection_command, attempt)
            if success:
                ticket_id = self._store.next_ticket_id(issued_at)
                inspection_event = build_inspection_requested_event(
                    ticket_id=ticket_id,
                    asset_id=event.data.asset_id,
                    requested_at=issued_at,
                    priority=priority,
                    reason=reason,
                    trace_id=event.trace_id,
                    produced_by=self._settings.event_produced_by,
                    correlation_id=workflow.workflow_id,
                )
                self._store.mark_inspection_requested(
                    workflow.workflow_id,
                    attempts=attempt,
                    ticket_id=ticket_id,
                    inspection_create_command=inspection_command,
                    inspection_requested_event=inspection_event,
                    updated_at=issued_at,
                )
                self._metrics.record_inspection_requested()
                self._metrics.record_decision_latency((perf_counter() - started) * 1000.0)
                return RiskDecision(
                    workflow_triggered=True,
                    workflow=self._store.get_workflow(workflow.workflow_id),
                    reason=reason,
                    retries_used=retries_used,
                    inspection_create_command=inspection_command,
                    inspection_requested_event=inspection_event,
                )

            self._store.record_attempt(
                workflow.workflow_id,
                attempts=attempt,
                last_error=error or "inspection dispatch failed",
                updated_at=issued_at,
            )
            if attempt < self._settings.max_retry_attempts:
                retries_used += 1
                self._metrics.record_retry()

        final_error = "inspection dispatch failed after max retries"
        failed_at = datetime.now(tz=timezone.utc)
        self._store.mark_failed(
            workflow.workflow_id,
            attempts=self._settings.max_retry_attempts,
            error=final_error,
            updated_at=failed_at,
        )
        self._metrics.record_workflow_failure()
        self._metrics.record_decision_latency((perf_counter() - started) * 1000.0)

        return RiskDecision(
            workflow_triggered=True,
            workflow=self._store.get_workflow(workflow.workflow_id),
            reason=f"{reason}; {final_error}",
            retries_used=retries_used,
            inspection_create_command=inspection_command,
            inspection_requested_event=None,
        )

    def complete_maintenance(
        self,
        *,
        workflow_id: str,
        performed_by: str,
        summary: str | None,
        completed_at: datetime | None = None,
    ) -> WorkflowRecord:
        """Mark workflow maintenance step complete and emit contract event payload."""

        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"workflow not found: {workflow_id}")

        if workflow.status == "maintenance_completed":
            return workflow

        if workflow.status != "inspection_requested":
            raise ValueError(f"workflow status '{workflow.status}' cannot complete maintenance")

        timestamp = completed_at or datetime.now(tz=timezone.utc)
        maintenance_id = self._store.next_maintenance_id(timestamp)
        maintenance_event = build_maintenance_completed_event(
            maintenance_id=maintenance_id,
            asset_id=workflow.asset_id,
            completed_at=timestamp,
            performed_by=performed_by,
            summary=summary,
            trace_id=workflow.trace_id,
            produced_by=self._settings.event_produced_by,
            correlation_id=workflow.workflow_id,
        )
        self._store.mark_maintenance_completed(
            workflow_id,
            maintenance_id=maintenance_id,
            event=maintenance_event,
            updated_at=timestamp,
        )
        self._metrics.record_maintenance_completed()

        result = self._store.get_workflow(workflow_id)
        if result is None:  # pragma: no cover
            raise KeyError(f"workflow disappeared after update: {workflow_id}")
        return result

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Return one workflow by ID."""

        return self._store.get_workflow(workflow_id)

    def list_workflows(self, *, asset_id: str | None = None, status: str | None = None) -> list[WorkflowRecord]:
        """Return workflows filtered by asset and/or status."""

        return self._store.list_workflows(asset_id=asset_id, status=status)

    @staticmethod
    def _default_dispatcher(command: dict[str, Any], attempt: int) -> tuple[bool, str | None]:
        del command, attempt
        return True, None

    def _dispatch_inspection_command(self, command: dict[str, Any], attempt: int) -> tuple[bool, str | None]:
        try:
            return self._inspection_dispatcher(command, attempt)
        except Exception as exc:  # pragma: no cover
            return False, str(exc)

    def _should_trigger(
        self,
        *,
        risk_level: str,
        health_score: float,
        failure_probability: float,
        anomaly_flag: int,
        forecast_available: bool,
    ) -> tuple[bool, str]:
        reasons: list[str] = []

        if risk_level in self._settings.trigger_risk_levels:
            reasons.append(f"risk_level={risk_level}")
        if health_score >= self._settings.min_health_score:
            reasons.append(f"health_score>={self._settings.min_health_score:.2f}")
        if failure_probability >= self._settings.min_failure_probability:
            source = "forecast_or_risk"
            if not forecast_available:
                source = "risk"
            reasons.append(f"{source}_failure_probability>={self._settings.min_failure_probability:.2f}")
        if anomaly_flag == 1 and risk_level in {"Moderate", "High", "Critical"}:
            reasons.append("anomaly_flag=1")

        if reasons:
            return True, "; ".join(reasons)
        return False, "event below orchestration trigger thresholds"

    @staticmethod
    def _priority_for(risk_level: str, failure_probability: float) -> str:
        if risk_level == "Critical" or failure_probability >= 0.85:
            return "critical"
        if risk_level == "High" or failure_probability >= 0.70:
            return "high"
        if risk_level == "Moderate":
            return "medium"
        return "low"
