"""In-memory dispatch store for notification service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from .schemas import DispatchAttemptDetail, DispatchStatus


@dataclass
class DispatchRecordMutable:
    """Mutable dispatch record persisted in memory."""

    dispatch_id: str
    command_id: str
    status: DispatchStatus
    primary_channel: str
    final_channel: str
    recipient: str
    severity: str
    rendered_message: str
    channels_tried: list[str]
    attempts_total: int
    retries_used: int
    fallback_used: bool
    created_at: datetime
    updated_at: datetime
    last_error: str | None
    attempt_log: list[DispatchAttemptDetail]
    delivery_status_event: dict


class InMemoryDispatchStore:
    """Thread-safe in-memory dispatch storage."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._counter = 0
            self._records: dict[str, DispatchRecordMutable] = {}

    def next_dispatch_id(self, now: datetime) -> str:
        with self._lock:
            self._counter += 1
            return f"dsp_{now.strftime('%Y%m%d')}_{self._counter:04d}"

    def put(self, record: DispatchRecordMutable) -> None:
        with self._lock:
            self._records[record.dispatch_id] = record

    def get(self, dispatch_id: str) -> DispatchRecordMutable | None:
        with self._lock:
            return self._records.get(dispatch_id)

    def list(
        self,
        *,
        status: str | None = None,
        recipient: str | None = None,
        channel: str | None = None,
        severity: str | None = None,
    ) -> list[DispatchRecordMutable]:
        with self._lock:
            records = list(self._records.values())

        if status:
            records = [record for record in records if record.status == status]
        if recipient:
            records = [record for record in records if record.recipient == recipient]
        if channel:
            records = [record for record in records if record.final_channel == channel]
        if severity:
            records = [record for record in records if record.severity == severity]

        return sorted(records, key=lambda record: record.created_at, reverse=True)
