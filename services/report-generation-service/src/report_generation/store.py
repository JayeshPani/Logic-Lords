"""In-memory context store for report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .schemas import EvidenceItem, InspectionRequestedEvent, MaintenanceCompletedEvent


@dataclass
class StoredInspection:
    """Stored inspection context keyed by asset."""

    event: InspectionRequestedEvent


@dataclass
class StoredMaintenance:
    """Stored maintenance context keyed by maintenance ID."""

    event: MaintenanceCompletedEvent


@dataclass
class StoredEvidence:
    """Stored organization evidence keyed by maintenance + evidence ID."""

    evidence_id: str
    maintenance_id: str
    asset_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_uri: str
    storage_object_path: str
    sha256_hex: str | None
    uploaded_by: str
    uploaded_at: datetime
    finalized_at: datetime | None
    status: str
    category: str | None
    notes: str | None


class InMemoryReportContextStore:
    """Thread-safe store for report-generation context and evidence records."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._inspection_by_asset: dict[str, StoredInspection] = {}
            self._maintenance_by_id: dict[str, StoredMaintenance] = {}
            self._evidence_by_maintenance: dict[str, dict[str, StoredEvidence]] = {}
            self._locked_maintenance_ids: set[str] = set()
            self._report_counter = 0
            self._evidence_counter = 0

    def put_inspection(self, event: InspectionRequestedEvent) -> None:
        with self._lock:
            self._inspection_by_asset[event.data.asset_id] = StoredInspection(event=event)

    def get_inspection(self, asset_id: str) -> InspectionRequestedEvent | None:
        with self._lock:
            stored = self._inspection_by_asset.get(asset_id)
            if stored is None:
                return None
            return stored.event

    def put_maintenance(self, event: MaintenanceCompletedEvent) -> None:
        with self._lock:
            self._maintenance_by_id[event.data.maintenance_id] = StoredMaintenance(event=event)

    def get_maintenance(self, maintenance_id: str) -> MaintenanceCompletedEvent | None:
        with self._lock:
            stored = self._maintenance_by_id.get(maintenance_id)
            if stored is None:
                return None
            return stored.event

    def next_report_id(self, now: datetime) -> str:
        with self._lock:
            self._report_counter += 1
            return f"rpt_{now.strftime('%Y%m%d')}_{self._report_counter:04d}"

    def next_evidence_id(self, now: datetime) -> str:
        with self._lock:
            self._evidence_counter += 1
            return f"evd_{now.strftime('%Y%m%d')}_{self._evidence_counter:04d}"

    def is_evidence_locked(self, maintenance_id: str) -> bool:
        with self._lock:
            return maintenance_id in self._locked_maintenance_ids

    def lock_evidence(self, maintenance_id: str) -> None:
        with self._lock:
            self._locked_maintenance_ids.add(maintenance_id)

    def create_evidence(
        self,
        *,
        evidence_id: str,
        maintenance_id: str,
        asset_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_uri: str,
        storage_object_path: str,
        uploaded_by: str,
        uploaded_at: datetime,
        category: str | None,
        notes: str | None,
    ) -> EvidenceItem:
        with self._lock:
            if maintenance_id in self._locked_maintenance_ids:
                raise ValueError("VERIFICATION_LOCKED")

            records = self._evidence_by_maintenance.setdefault(maintenance_id, {})
            if evidence_id in records:
                raise ValueError("EVIDENCE_ID_CONFLICT")

            records[evidence_id] = StoredEvidence(
                evidence_id=evidence_id,
                maintenance_id=maintenance_id,
                asset_id=asset_id,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_uri=storage_uri,
                storage_object_path=storage_object_path,
                sha256_hex=None,
                uploaded_by=uploaded_by,
                uploaded_at=uploaded_at,
                finalized_at=None,
                status="upload_pending",
                category=category,
                notes=notes,
            )
            return self._to_evidence_item(records[evidence_id])

    def get_evidence(self, maintenance_id: str, evidence_id: str) -> EvidenceItem | None:
        with self._lock:
            record = self._evidence_by_maintenance.get(maintenance_id, {}).get(evidence_id)
            if record is None:
                return None
            return self._to_evidence_item(record)

    def get_evidence_storage_object_path(self, maintenance_id: str, evidence_id: str) -> str | None:
        with self._lock:
            record = self._evidence_by_maintenance.get(maintenance_id, {}).get(evidence_id)
            if record is None:
                return None
            return record.storage_object_path

    def list_evidence(self, maintenance_id: str) -> list[EvidenceItem]:
        with self._lock:
            records = list(self._evidence_by_maintenance.get(maintenance_id, {}).values())

        records.sort(key=lambda item: item.evidence_id)
        return [self._to_evidence_item(record) for record in records]

    def list_finalized_evidence(self, maintenance_id: str) -> list[EvidenceItem]:
        with self._lock:
            records = [
                record
                for record in self._evidence_by_maintenance.get(maintenance_id, {}).values()
                if record.status == "finalized"
            ]

        records.sort(key=lambda item: item.evidence_id)
        return [self._to_evidence_item(record) for record in records]

    def finalize_evidence(
        self,
        *,
        maintenance_id: str,
        evidence_id: str,
        sha256_hex: str,
        size_bytes: int,
        content_type: str,
        finalized_at: datetime,
        finalized_by: str,
    ) -> EvidenceItem:
        with self._lock:
            if maintenance_id in self._locked_maintenance_ids:
                raise ValueError("VERIFICATION_LOCKED")

            record = self._evidence_by_maintenance.get(maintenance_id, {}).get(evidence_id)
            if record is None:
                raise KeyError("EVIDENCE_NOT_FOUND")
            if record.status == "deleted":
                raise ValueError("EVIDENCE_DELETED")

            record.sha256_hex = sha256_hex
            record.size_bytes = size_bytes
            record.content_type = content_type
            record.finalized_at = finalized_at
            record.uploaded_by = finalized_by
            record.status = "finalized"
            return self._to_evidence_item(record)

    def delete_evidence(self, *, maintenance_id: str, evidence_id: str) -> EvidenceItem:
        with self._lock:
            if maintenance_id in self._locked_maintenance_ids:
                raise ValueError("VERIFICATION_LOCKED")

            record = self._evidence_by_maintenance.get(maintenance_id, {}).get(evidence_id)
            if record is None:
                raise KeyError("EVIDENCE_NOT_FOUND")

            record.status = "deleted"
            return self._to_evidence_item(record)

    @staticmethod
    def _to_evidence_item(record: StoredEvidence) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=record.evidence_id,
            maintenance_id=record.maintenance_id,
            asset_id=record.asset_id,
            filename=record.filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            storage_uri=record.storage_uri,
            storage_object_path=record.storage_object_path,
            sha256_hex=record.sha256_hex,
            uploaded_by=record.uploaded_by,
            uploaded_at=record.uploaded_at,
            finalized_at=record.finalized_at,
            status=record.status,
            category=record.category,
            notes=record.notes,
        )
