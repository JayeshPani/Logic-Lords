"""In-memory store for blockchain verification records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock


@dataclass
class VerificationRecordMutable:
    """Mutable in-memory verification record."""

    verification_id: str
    command_id: str
    maintenance_id: str
    asset_id: str
    verification_status: str
    evidence_hash: str
    tx_hash: str | None
    network: str
    contract_address: str
    chain_id: int
    block_number: int | None
    confirmations: int
    required_confirmations: int
    submitted_at: datetime | None
    confirmed_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    trace_id: str
    maintenance_verified_event: dict | None = None


class InMemoryVerificationStore:
    """Thread-safe state for verification lifecycle."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._counter = 0
            self._records_by_maintenance: dict[str, VerificationRecordMutable] = {}

    def next_verification_id(self, now: datetime) -> str:
        with self._lock:
            self._counter += 1
            return f"vfy_{now.strftime('%Y%m%d')}_{self._counter:04d}"

    def put(self, record: VerificationRecordMutable) -> None:
        with self._lock:
            self._records_by_maintenance[record.maintenance_id] = record

    def get(self, maintenance_id: str) -> VerificationRecordMutable | None:
        with self._lock:
            return self._records_by_maintenance.get(maintenance_id)

    def list(self, *, status: str | None = None, asset_id: str | None = None) -> list[VerificationRecordMutable]:
        with self._lock:
            records = list(self._records_by_maintenance.values())

        if status:
            records = [record for record in records if record.verification_status == status]
        if asset_id:
            records = [record for record in records if record.asset_id == asset_id]

        return sorted(records, key=lambda record: record.created_at, reverse=True)
