"""Core orchestration workflow logic for high-risk automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import socket
from time import perf_counter
from typing import Any, Callable
from urllib import error as url_error
from urllib import request as url_request

from .config import Settings
from .events import (
    build_inspection_create_command,
    build_inspection_requested_event,
    build_maintenance_completed_event,
    build_notification_dispatch_command,
    build_report_generate_request,
)
from .observability import OrchestrationMetrics
from .schemas import AssetFailurePredictedEvent, AssetRiskComputedEvent
from .store import ForecastSnapshot, InMemoryOrchestrationStore, WorkflowRecord


InspectionDispatcher = Callable[[dict[str, Any], int], tuple[bool, str | None]]
NotificationDispatcher = Callable[[dict[str, Any], float], tuple[bool, str | None, str | None]]


@dataclass(frozen=True)
class RiskDecision:
    """Outcome of handling one `asset.risk.computed` event."""

    workflow_triggered: bool
    workflow: WorkflowRecord | None
    reason: str
    retries_used: int
    inspection_create_command: dict[str, Any] | None
    inspection_requested_event: dict[str, Any] | None


@dataclass(frozen=True)
class VerificationPipelineResult:
    """Result of report-generation + verification handoff."""

    verification_status: str
    verification_maintenance_id: str | None
    verification_tx_hash: str | None
    verification_error: str | None


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
        self._notification_dispatcher: NotificationDispatcher = self._default_notification_dispatcher

    def reset_state_for_tests(self) -> None:
        """Reset store and dispatchers for deterministic tests."""

        self._store.reset()
        self._inspection_dispatcher = self._default_dispatcher
        self._notification_dispatcher = self._default_notification_dispatcher

    def set_inspection_dispatcher_for_tests(self, dispatcher: InspectionDispatcher) -> None:
        """Inject test dispatcher to exercise inspection retry behavior."""

        self._inspection_dispatcher = dispatcher

    def set_notification_dispatcher_for_tests(self, dispatcher: NotificationDispatcher) -> None:
        """Inject test dispatcher to exercise notification behavior."""

        self._notification_dispatcher = dispatcher

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

                # Phase-1 safety escalation: notify management and start ACK SLA timer.
                deadline_at = issued_at + timedelta(minutes=max(self._settings.authority_ack_sla_minutes, 1))
                management_dispatch_ids = self._dispatch_management_notifications(
                    workflow=workflow,
                    risk_level=event.data.risk_level,
                    effective_failure_probability=effective_failure_probability,
                    deadline_at=deadline_at,
                )
                self._store.mark_management_notified(
                    workflow.workflow_id,
                    notified_at=issued_at,
                    ack_deadline_at=deadline_at,
                    dispatch_ids=management_dispatch_ids,
                    updated_at=issued_at,
                )
                self._metrics.record_management_notified()

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

    def process_ack_deadline_timeouts(self, now: datetime | None = None) -> list[WorkflowRecord]:
        """Escalate unacknowledged incidents to police after SLA expiry."""

        current_time = now or datetime.now(tz=timezone.utc)
        candidates = self._store.list_ack_timeout_candidates(current_time)
        escalated: list[WorkflowRecord] = []

        for workflow in candidates:
            dispatch_ids = self._dispatch_police_notifications(workflow=workflow)
            changed = self._store.mark_police_notified(
                workflow.workflow_id,
                notified_at=current_time,
                dispatch_ids=dispatch_ids,
                updated_at=current_time,
            )
            if not changed:
                continue
            self._metrics.record_police_notified()
            updated = self._store.get_workflow(workflow.workflow_id)
            if updated is not None:
                escalated.append(updated)

        return escalated

    def acknowledge_incident(
        self,
        *,
        workflow_id: str,
        acknowledged_by: str,
        ack_notes: str | None,
        acknowledged_at: datetime | None = None,
    ) -> WorkflowRecord:
        """Record management acknowledgement and stop further escalation."""

        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"workflow not found: {workflow_id}")

        if workflow.escalation_stage is None:
            raise ValueError(f"workflow '{workflow_id}' has no active incident")

        already_acknowledged = workflow.acknowledged_at is not None
        timestamp = acknowledged_at or datetime.now(tz=timezone.utc)

        updated = self._store.acknowledge(
            workflow_id,
            acknowledged_at=timestamp,
            acknowledged_by=acknowledged_by,
            ack_notes=ack_notes,
        )
        if updated is None:  # pragma: no cover
            raise KeyError(f"workflow not found: {workflow_id}")

        if not already_acknowledged:
            self._metrics.record_acknowledged()

        return updated

    def complete_maintenance(
        self,
        *,
        workflow_id: str,
        performed_by: str,
        summary: str | None,
        operator_wallet_address: str | None = None,
        completed_at: datetime | None = None,
    ) -> WorkflowRecord:
        """Complete maintenance and prepare evidence-aware verification state."""

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

        context_error = self._ingest_report_generation_context(
            workflow_id=workflow_id,
            maintenance_event=maintenance_event,
        )
        self._store.mark_verification_result(
            workflow_id,
            verification_status="awaiting_evidence",
            verification_maintenance_id=maintenance_id,
            verification_tx_hash=None,
            verification_error=context_error,
            updated_at=datetime.now(tz=timezone.utc),
        )

        result = self._store.get_workflow(workflow_id)
        if result is None:  # pragma: no cover
            raise KeyError(f"workflow disappeared after update: {workflow_id}")
        return result

    def submit_verification_by_maintenance_id(
        self,
        *,
        maintenance_id: str,
        submitted_by: str,
        operator_wallet_address: str | None = None,
    ) -> WorkflowRecord:
        """Submit verification after evidence upload is complete."""

        workflow = self._store.get_workflow_by_maintenance_id(maintenance_id)
        if workflow is None:
            raise KeyError(f"maintenance workflow not found: {maintenance_id}")

        if workflow.status != "maintenance_completed":
            raise ValueError(f"workflow status '{workflow.status}' cannot submit verification")

        if workflow.verification_status in {"submitted", "pending", "confirmed"} and not workflow.verification_error:
            return workflow

        maintenance_event = workflow.maintenance_completed_event
        if not isinstance(maintenance_event, dict):
            raise ValueError("maintenance event context missing for verification submit")

        result = self._run_verification_pipeline(
            workflow_id=workflow.workflow_id,
            maintenance_id=maintenance_id,
            maintenance_event=maintenance_event,
            operator_wallet_address=operator_wallet_address,
            started_at=datetime.now(tz=timezone.utc),
            submitted_by=submitted_by,
        )
        self._store.mark_verification_result(
            workflow.workflow_id,
            verification_status=result.verification_status,
            verification_maintenance_id=result.verification_maintenance_id,
            verification_tx_hash=result.verification_tx_hash,
            verification_error=result.verification_error,
            updated_at=datetime.now(tz=timezone.utc),
        )

        updated = self._store.get_workflow(workflow.workflow_id)
        if updated is None:  # pragma: no cover
            raise KeyError(f"workflow disappeared after verification submit: {workflow.workflow_id}")
        return updated

    def get_verification_state_by_maintenance_id(self, maintenance_id: str) -> WorkflowRecord:
        """Fetch workflow verification state for one maintenance ID."""

        workflow = self._store.get_workflow_by_maintenance_id(maintenance_id)
        if workflow is None:
            raise KeyError(f"maintenance workflow not found: {maintenance_id}")
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Return one workflow by ID."""

        return self._store.get_workflow(workflow_id)

    def list_workflows(self, *, asset_id: str | None = None, status: str | None = None) -> list[WorkflowRecord]:
        """Return workflows filtered by asset and/or status."""

        return self._store.list_workflows(asset_id=asset_id, status=status)

    def list_incidents(self) -> list[WorkflowRecord]:
        """Return workflows participating in escalation lifecycle."""

        return [
            workflow
            for workflow in self._store.list_workflows()
            if workflow.escalation_stage is not None
        ]

    @staticmethod
    def _default_dispatcher(command: dict[str, Any], attempt: int) -> tuple[bool, str | None]:
        del command, attempt
        return True, None

    def _dispatch_inspection_command(self, command: dict[str, Any], attempt: int) -> tuple[bool, str | None]:
        try:
            return self._inspection_dispatcher(command, attempt)
        except Exception as exc:  # pragma: no cover
            return False, str(exc)

    def _dispatch_notification_command(self, command: dict[str, Any]) -> tuple[bool, str | None, str | None]:
        timeout_seconds = max(self._settings.notification_timeout_seconds, 0.1)
        try:
            return self._notification_dispatcher(command, timeout_seconds)
        except Exception as exc:  # pragma: no cover
            return False, None, str(exc)

    def _dispatch_management_notifications(
        self,
        *,
        workflow: WorkflowRecord,
        risk_level: str,
        effective_failure_probability: float,
        deadline_at: datetime,
    ) -> list[str]:
        severity = self._severity_for_risk(risk_level)
        zone = self._zone_from_asset_id(workflow.asset_id)
        context = {
            "asset_id": workflow.asset_id,
            "workflow_id": workflow.workflow_id,
            "risk_level": risk_level,
            "failure_probability_72h": round(effective_failure_probability, 4),
            "deadline_at": deadline_at.isoformat(),
            "zone": zone,
            "recommended_action": "Acknowledge incident and start maintenance response.",
        }
        message = (
            f"High-risk infrastructure incident for {workflow.asset_id} in zone {zone}. "
            f"Management acknowledgement required within {max(self._settings.authority_ack_sla_minutes, 1)} minutes."
        )

        return self._dispatch_notification_group(
            recipients=self._settings.management_recipients,
            channels=self._settings.management_channels,
            message=message,
            severity=severity,
            context=context,
            trace_id=workflow.trace_id,
            correlation_id=workflow.workflow_id,
        )

    def _dispatch_police_notifications(self, *, workflow: WorkflowRecord) -> list[str]:
        zone = self._zone_from_asset_id(workflow.asset_id)
        context = {
            "asset_id": workflow.asset_id,
            "workflow_id": workflow.workflow_id,
            "risk_priority": workflow.priority,
            "zone": zone,
            "recommended_action": "Danger area restriction recommended until maintenance authority responds.",
            "ack_deadline_at": workflow.authority_ack_deadline_at.isoformat() if workflow.authority_ack_deadline_at else None,
        }
        message = (
            f"URGENT public-safety escalation for {workflow.asset_id} in zone {zone}. "
            "Management acknowledgement missed SLA. Restrict public access to the area."
        )

        return self._dispatch_notification_group(
            recipients=self._settings.police_recipients,
            channels=self._settings.police_channels,
            message=message,
            severity="critical",
            context=context,
            trace_id=workflow.trace_id,
            correlation_id=workflow.workflow_id,
        )

    def _dispatch_notification_group(
        self,
        *,
        recipients: tuple[str, ...],
        channels: tuple[str, ...],
        message: str,
        severity: str,
        context: dict[str, Any],
        trace_id: str,
        correlation_id: str,
    ) -> list[str]:
        if not recipients or not channels:
            return []

        primary_channel = channels[0]
        fallback_channels = list(channels[1:]) or None
        dispatch_ids: list[str] = []

        for recipient in recipients:
            command = build_notification_dispatch_command(
                channel=primary_channel,
                fallback_channels=fallback_channels,
                recipient=recipient,
                message=message,
                severity=severity,
                context=context,
                trace_id=trace_id,
                requested_by=self._settings.command_requested_by,
                requested_at=datetime.now(tz=timezone.utc),
                correlation_id=correlation_id,
            )
            _success, dispatch_id, _error = self._dispatch_notification_command(command)
            if dispatch_id:
                dispatch_ids.append(dispatch_id)

        return dispatch_ids

    def _ingest_report_generation_context(
        self,
        *,
        workflow_id: str,
        maintenance_event: dict[str, Any],
    ) -> str | None:
        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            return f"verification workflow not found: {workflow_id}"

        inspection_event = workflow.inspection_requested_event
        if not isinstance(inspection_event, dict):
            return "missing inspection context for report generation"

        try:
            self._request_json(
                base_url=self._settings.report_generation_base_url,
                path="/events/inspection-requested",
                timeout_seconds=self._settings.report_generation_timeout_seconds,
                payload=inspection_event,
                purpose="report context ingestion (inspection)",
            )
            self._request_json(
                base_url=self._settings.report_generation_base_url,
                path="/events/maintenance-completed",
                timeout_seconds=self._settings.report_generation_timeout_seconds,
                payload=maintenance_event,
                purpose="report context ingestion (maintenance)",
            )
            return None
        except Exception as exc:  # pragma: no cover - downstream dependency failures
            message = str(exc).strip() or "report context ingestion failed"
            if len(message) > 320:
                message = message[:320]
            return message

    def _run_verification_pipeline(
        self,
        *,
        workflow_id: str,
        maintenance_id: str,
        maintenance_event: dict[str, Any],
        operator_wallet_address: str | None,
        started_at: datetime,
        submitted_by: str,
    ) -> VerificationPipelineResult:
        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            return VerificationPipelineResult(
                verification_status="failed",
                verification_maintenance_id=maintenance_id,
                verification_tx_hash=None,
                verification_error=f"verification workflow not found: {workflow_id}",
            )

        inspection_event = workflow.inspection_requested_event
        if not isinstance(inspection_event, dict):
            return VerificationPipelineResult(
                verification_status="failed",
                verification_maintenance_id=maintenance_id,
                verification_tx_hash=None,
                verification_error="missing inspection context for report generation",
            )

        try:
            context_error = self._ingest_report_generation_context(
                workflow_id=workflow_id,
                maintenance_event=maintenance_event,
            )
            if context_error is not None:
                raise RuntimeError(context_error)

            report_request = build_report_generate_request(
                maintenance_id=maintenance_id,
                asset_id=workflow.asset_id,
                trace_id=workflow.trace_id,
                requested_by=submitted_by,
                requested_at=started_at,
                correlation_id=workflow.workflow_id,
                generated_at=started_at,
            )
            if operator_wallet_address:
                command_metadata = report_request["command"].setdefault("metadata", {})
                command_metadata["operator_wallet_address"] = operator_wallet_address.lower()
            report_metadata = report_request["command"].setdefault("metadata", {})
            report_metadata["submitted_by"] = submitted_by

            report_response = self._request_json(
                base_url=self._settings.report_generation_base_url,
                path="/generate",
                timeout_seconds=self._settings.report_generation_timeout_seconds,
                payload=report_request,
                purpose="report generation",
            )
            verification_command = report_response.get("verification_record_command")
            if not isinstance(verification_command, dict):
                raise ValueError("report generation response missing verification_record_command")
            if operator_wallet_address:
                command_metadata = verification_command.setdefault("metadata", {})
                command_metadata["operator_wallet_address"] = operator_wallet_address.lower()
            verification_metadata = verification_command.setdefault("metadata", {})
            verification_metadata["submitted_by"] = submitted_by

            verification_response = self._request_json(
                base_url=self._settings.blockchain_verification_base_url,
                path="/record",
                timeout_seconds=self._settings.blockchain_verification_timeout_seconds,
                payload=verification_command,
                purpose="blockchain verification record",
            )
            verification = verification_response.get("verification")
            if not isinstance(verification, dict):
                raise ValueError("blockchain verification response missing verification payload")

            verification_status = str(verification.get("verification_status") or "submitted").lower()
            verification_maintenance_id = str(verification.get("maintenance_id") or maintenance_id)
            tx_hash = verification.get("tx_hash")
            if tx_hash is not None:
                tx_hash = str(tx_hash)

            return VerificationPipelineResult(
                verification_status=verification_status,
                verification_maintenance_id=verification_maintenance_id,
                verification_tx_hash=tx_hash,
                verification_error=None,
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            message = str(exc).strip() or "verification pipeline failed"
            if len(message) > 320:
                message = message[:320]
            return VerificationPipelineResult(
                verification_status="failed",
                verification_maintenance_id=maintenance_id,
                verification_tx_hash=None,
                verification_error=message,
            )

    def _request_json(
        self,
        *,
        base_url: str,
        path: str,
        timeout_seconds: float,
        payload: dict[str, Any],
        purpose: str,
    ) -> dict[str, Any]:
        endpoint = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        request = url_request.Request(
            url=endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
            },
        )

        try:
            with url_request.urlopen(request, timeout=max(timeout_seconds, 0.1)) as response:
                raw = response.read().decode("utf-8")
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{purpose} failed with HTTP {exc.code}: {details[:180]}") from exc
        except url_error.URLError as exc:
            raise RuntimeError(f"{purpose} unavailable: {exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(f"{purpose} timed out after {max(timeout_seconds, 0.1):.1f}s") from exc
        except OSError as exc:
            raise RuntimeError(f"{purpose} network error: {exc}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{purpose} returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise RuntimeError(f"{purpose} returned unsupported payload shape")
        return body

    def _default_notification_dispatcher(
        self,
        command: dict[str, Any],
        timeout_seconds: float,
    ) -> tuple[bool, str | None, str | None]:
        endpoint = f"{self._settings.notification_base_url.rstrip('/')}/dispatch"
        request = url_request.Request(
            url=endpoint,
            data=json.dumps(command).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
            },
        )

        try:
            with url_request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            return False, None, f"notification HTTP {exc.code}: {details[:180]}"
        except url_error.URLError as exc:
            return False, None, f"notification unavailable: {exc.reason}"
        except (TimeoutError, socket.timeout):
            return False, None, f"notification timeout after {timeout_seconds:.1f}s"
        except OSError as exc:
            return False, None, f"notification network error: {exc}"

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            return False, None, "notification returned invalid JSON"

        dispatch = body.get("dispatch") if isinstance(body, dict) else None
        if not isinstance(dispatch, dict):
            return False, None, "notification response missing dispatch payload"

        dispatch_id = dispatch.get("dispatch_id")
        status = str(dispatch.get("status", "failed")).lower()
        if status == "delivered":
            return True, dispatch_id, None
        return False, dispatch_id, dispatch.get("last_error") or "notification delivery failed"

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

    @staticmethod
    def _severity_for_risk(risk_level: str) -> str:
        if risk_level == "Critical":
            return "critical"
        if risk_level == "High":
            return "warning"
        if risk_level == "Moderate":
            return "watch"
        return "healthy"

    @staticmethod
    def _zone_from_asset_id(asset_id: str) -> str:
        parts = asset_id.split("_")
        if len(parts) >= 3:
            return parts[1].upper()
        return "UNKNOWN"
