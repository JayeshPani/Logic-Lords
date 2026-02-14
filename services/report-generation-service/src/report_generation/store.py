"""In-memory context store for report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .schemas import InspectionRequestedEvent, MaintenanceCompletedEvent


@dataclass
class StoredInspection:
    """Stored inspection context keyed by asset."""

    event: InspectionRequestedEvent


@dataclass
class StoredMaintenance:
    """Stored maintenance context keyed by maintenance ID."""

    event: MaintenanceCompletedEvent


class InMemoryReportContextStore:
    """Thread-safe store for report-generation context."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._inspection_by_asset: dict[str, StoredInspection] = {}
            self._maintenance_by_id: dict[str, StoredMaintenance] = {}
            self._report_counter = 0

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
