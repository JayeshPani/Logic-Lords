"""Core logic for building report bundles and downstream messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from .config import Settings
from .events import build_report_generated_event, build_verification_record_command
from .schemas import (
    EvidenceItem,
    GenerateReportRequest,
    GenerateReportResponse,
    InspectionRequestedEvent,
    MaintenanceCompletedEvent,
    ReportBundle,
    ReportGenerateCommand,
    SourceTraceRef,
)
from .store import InMemoryReportContextStore


@dataclass(frozen=True)
class GeneratedReportArtifacts:
    """Generated artifacts grouped for easier testing."""

    bundle: ReportBundle
    report_generated_event: dict
    verification_record_command: dict


class ReportGenerationEngine:
    """Coordinates context loading, report rendering, and message generation."""

    def __init__(self, *, settings: Settings, store: InMemoryReportContextStore) -> None:
        self._settings = settings
        self._store = store

    def reset_state_for_tests(self) -> None:
        """Reset context store for deterministic tests."""

        self._store.reset()

    def ingest_inspection_context(self, event: InspectionRequestedEvent) -> None:
        """Store inspection context event."""

        self._store.put_inspection(event)

    def ingest_maintenance_context(self, event: MaintenanceCompletedEvent) -> None:
        """Store maintenance context event."""

        self._store.put_maintenance(event)

    def generate(self, request: GenerateReportRequest) -> GenerateReportResponse:
        """Generate report bundle and output messages from command + context."""

        command = request.command
        now = request.generated_at or datetime.now(tz=timezone.utc)

        maintenance = self._store.get_maintenance(command.payload.maintenance_id)
        if maintenance is None:
            raise KeyError(f"maintenance context not found: {command.payload.maintenance_id}")

        inspection = self._store.get_inspection(command.payload.asset_id)
        uploaded_evidence = self._store.list_finalized_evidence(command.payload.maintenance_id)
        if command.payload.report_type == "maintenance_verification" and not uploaded_evidence:
            raise ValueError("EVIDENCE_REQUIRED: at least one finalized evidence file is required.")

        source_traces = self._build_source_traces(command, maintenance, inspection)
        evidence_hash = self._compute_evidence_hash(
            command,
            maintenance,
            inspection,
            uploaded_evidence,
            now,
        )
        report_id = self._store.next_report_id(now)

        summary = self._build_summary(command, maintenance, inspection)
        sections = self._build_sections(command, maintenance, inspection, uploaded_evidence)

        bundle = ReportBundle(
            report_id=report_id,
            maintenance_id=command.payload.maintenance_id,
            asset_id=command.payload.asset_id,
            report_type=command.payload.report_type,
            generated_at=now,
            evidence_hash=evidence_hash,
            summary=summary,
            source_traces=source_traces,
            sections=sections,
        )

        source_trace_ids = [trace.trace_id for trace in source_traces]
        source_event_ids = [str(command.command_id), str(maintenance.event_id)]
        if inspection is not None:
            source_event_ids.append(str(inspection.event_id))

        report_event = build_report_generated_event(
            report_id=report_id,
            maintenance_id=command.payload.maintenance_id,
            asset_id=command.payload.asset_id,
            report_type=command.payload.report_type,
            generated_at=now,
            evidence_hash=evidence_hash,
            source_trace_ids=source_trace_ids,
            source_event_ids=source_event_ids,
            trace_id=command.trace_id,
            produced_by=self._settings.event_produced_by,
            correlation_id=command.correlation_id,
        )

        verification_command = build_verification_record_command(
            maintenance_id=command.payload.maintenance_id,
            asset_id=command.payload.asset_id,
            evidence_hash=evidence_hash,
            network=self._settings.blockchain_network,
            contract_address=self._settings.blockchain_contract_address,
            chain_id=self._settings.blockchain_chain_id,
            trace_id=command.trace_id,
            requested_by=self._settings.command_requested_by,
            requested_at=now,
            correlation_id=command.correlation_id,
        )

        self._store.lock_evidence(command.payload.maintenance_id)

        return GenerateReportResponse(
            report_bundle=bundle,
            report_generated_event=report_event,
            verification_record_command=verification_command,
        )

    def _compute_evidence_hash(
        self,
        command: ReportGenerateCommand,
        maintenance: MaintenanceCompletedEvent,
        inspection: InspectionRequestedEvent | None,
        uploaded_evidence: list[EvidenceItem],
        generated_at: datetime,
    ) -> str:
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "sha256_hex": item.sha256_hex,
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
                "storage_uri": item.storage_uri,
            }
            for item in sorted(uploaded_evidence, key=lambda value: value.evidence_id)
        ]
        payload = {
            "command": command.model_dump(mode="json", by_alias=True, exclude_none=True),
            "maintenance": maintenance.model_dump(mode="json", by_alias=True, exclude_none=True),
            "inspection": (
                inspection.model_dump(mode="json", by_alias=True, exclude_none=True)
                if inspection is not None
                else None
            ),
            "uploaded_evidence": evidence_payload,
            "generated_at": generated_at.isoformat(),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"0x{digest}"

    @staticmethod
    def _build_summary(
        command: ReportGenerateCommand,
        maintenance: MaintenanceCompletedEvent,
        inspection: InspectionRequestedEvent | None,
    ) -> str:
        if command.payload.report_type == "maintenance_verification":
            summary = (
                f"Maintenance verification report for {command.payload.asset_id}; "
                f"work completed by {maintenance.data.performed_by} at {maintenance.data.completed_at.isoformat()}."
            )
        else:
            summary = (
                f"Inspection report for {command.payload.asset_id}; "
                f"maintenance reference {command.payload.maintenance_id}."
            )
        if inspection is not None:
            summary += f" Inspection priority {inspection.data.priority}."
        return summary

    @staticmethod
    def _build_sections(
        command: ReportGenerateCommand,
        maintenance: MaintenanceCompletedEvent,
        inspection: InspectionRequestedEvent | None,
        uploaded_evidence: list[EvidenceItem],
    ) -> dict[str, str | int | float | bool | list[str] | dict[str, str]]:
        sections: dict[str, str | int | float | bool | list[str] | dict[str, str]] = {
            "asset": command.payload.asset_id,
            "maintenance_id": command.payload.maintenance_id,
            "report_type": command.payload.report_type,
            "maintenance_performed_by": maintenance.data.performed_by,
            "maintenance_completed_at": maintenance.data.completed_at.isoformat(),
            "maintenance_summary": maintenance.data.summary or "",
            "uploaded_evidence_count": len(uploaded_evidence),
            "uploaded_evidence_ids": [item.evidence_id for item in uploaded_evidence],
        }
        if command.payload.include_sensor_window is not None:
            sections["sensor_window"] = {
                "from": command.payload.include_sensor_window.from_.isoformat(),
                "to": command.payload.include_sensor_window.to.isoformat(),
            }
        if inspection is not None:
            sections["inspection_ticket_id"] = inspection.data.ticket_id
            sections["inspection_reason"] = inspection.data.reason
            sections["inspection_priority"] = inspection.data.priority
        return sections

    @staticmethod
    def _build_source_traces(
        command: ReportGenerateCommand,
        maintenance: MaintenanceCompletedEvent,
        inspection: InspectionRequestedEvent | None,
    ) -> list[SourceTraceRef]:
        traces = [
            SourceTraceRef(
                message_id=str(command.command_id),
                message_type=command.command_type,
                trace_id=command.trace_id,
                produced_by=command.requested_by,
                occurred_at=command.requested_at,
            ),
            SourceTraceRef(
                message_id=str(maintenance.event_id),
                message_type=maintenance.event_type,
                trace_id=maintenance.trace_id,
                produced_by=maintenance.produced_by,
                occurred_at=maintenance.occurred_at,
            ),
        ]
        if inspection is not None:
            traces.append(
                SourceTraceRef(
                    message_id=str(inspection.event_id),
                    message_type=inspection.event_type,
                    trace_id=inspection.trace_id,
                    produced_by=inspection.produced_by,
                    occurred_at=inspection.occurred_at,
                )
            )
        return traces
