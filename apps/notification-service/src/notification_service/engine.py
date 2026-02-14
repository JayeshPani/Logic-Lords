"""Core dispatch logic for notification service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .config import Settings
from .events import build_notification_delivery_status_event
from .observability import NotificationMetrics
from .schemas import DispatchAttemptDetail, NotificationDispatchCommand
from .store import DispatchRecordMutable, InMemoryDispatchStore
from .templates import render_message


DispatchChannelHandler = Callable[
    [str, str, int, dict[str, str | int | float | bool | None] | None],
    tuple[bool, str | None],
]


@dataclass(frozen=True)
class DispatchDecision:
    """Dispatch result with persisted record."""

    record: DispatchRecordMutable


class NotificationEngine:
    """Handles dispatch retries, fallback routing, and status event generation."""

    CHANNELS = ("email", "sms", "webhook", "chat")

    def __init__(
        self,
        *,
        settings: Settings,
        store: InMemoryDispatchStore,
        metrics: NotificationMetrics,
    ) -> None:
        self._settings = settings
        self._store = store
        self._metrics = metrics
        self._dispatchers: dict[str, DispatchChannelHandler] = {
            channel: self._default_dispatcher for channel in self.CHANNELS
        }

    def reset_state_for_tests(self) -> None:
        """Reset state for deterministic tests."""

        self._store.reset()
        self._dispatchers = {channel: self._default_dispatcher for channel in self.CHANNELS}

    def set_channel_dispatcher_for_tests(self, channel: str, handler: DispatchChannelHandler) -> None:
        """Inject channel-specific dispatcher for tests."""

        if channel not in self.CHANNELS:
            raise ValueError(f"unsupported channel: {channel}")
        self._dispatchers[channel] = handler

    def dispatch(self, command: NotificationDispatchCommand) -> DispatchDecision:
        """Dispatch one notification with retry and fallback policy."""

        created_at = datetime.now(tz=timezone.utc)
        dispatch_id = self._store.next_dispatch_id(created_at)
        rendered_message = render_message(
            severity=command.payload.severity,
            message=command.payload.message,
            context=command.payload.context,
        )

        channels = self._channel_sequence(command.payload.channel, command.payload.fallback_channels)
        attempts_total = 0
        retries_used = 0
        fallback_used = False
        channels_tried: list[str] = []
        attempt_log: list[DispatchAttemptDetail] = []
        last_error: str | None = None

        status = "failed"
        final_channel = command.payload.channel
        updated_at = created_at

        for index, channel in enumerate(channels):
            if index > 0:
                fallback_used = True
                self._metrics.record_fallback_switch()

            channels_tried.append(channel)
            dispatcher = self._dispatchers[channel]

            for attempt in range(1, self._settings.max_retry_attempts + 1):
                attempts_total += 1
                attempt_time = datetime.now(tz=timezone.utc)

                try:
                    success, error = dispatcher(
                        command.payload.recipient,
                        rendered_message,
                        attempt,
                        command.payload.context,
                    )
                except Exception as exc:  # pragma: no cover
                    success = False
                    error = str(exc)

                attempt_log.append(
                    DispatchAttemptDetail(
                        channel=channel,
                        attempt=attempt,
                        succeeded=success,
                        attempted_at=attempt_time,
                        error=error,
                    )
                )

                if success:
                    status = "delivered"
                    final_channel = channel
                    last_error = None
                    updated_at = attempt_time
                    break

                last_error = error or "delivery failed"
                updated_at = attempt_time
                if attempt < self._settings.max_retry_attempts:
                    retries_used += 1
                    self._metrics.record_retry()

            if status == "delivered":
                break

        if status == "failed" and channels_tried:
            final_channel = channels_tried[-1]

        event = build_notification_delivery_status_event(
            dispatch_id=dispatch_id,
            command_id=str(command.command_id),
            status=status,
            channel=final_channel,
            recipient=command.payload.recipient,
            severity=command.payload.severity,
            attempts=attempts_total,
            retries_used=retries_used,
            fallback_used=fallback_used,
            channels_tried=channels_tried,
            updated_at=updated_at,
            trace_id=command.trace_id,
            produced_by=self._settings.event_produced_by,
            error=last_error,
            correlation_id=command.correlation_id,
        )

        record = DispatchRecordMutable(
            dispatch_id=dispatch_id,
            command_id=str(command.command_id),
            status=status,
            primary_channel=command.payload.channel,
            final_channel=final_channel,
            recipient=command.payload.recipient,
            severity=command.payload.severity,
            rendered_message=rendered_message,
            channels_tried=channels_tried,
            attempts_total=attempts_total,
            retries_used=retries_used,
            fallback_used=fallback_used,
            created_at=created_at,
            updated_at=updated_at,
            last_error=last_error,
            attempt_log=attempt_log,
            delivery_status_event=event,
        )
        self._store.put(record)

        return DispatchDecision(record=record)

    def get_dispatch(self, dispatch_id: str) -> DispatchRecordMutable | None:
        """Get one dispatch record."""

        return self._store.get(dispatch_id)

    def list_dispatches(
        self,
        *,
        status: str | None = None,
        recipient: str | None = None,
        channel: str | None = None,
        severity: str | None = None,
    ) -> list[DispatchRecordMutable]:
        """List dispatch records with optional filters."""

        return self._store.list(status=status, recipient=recipient, channel=channel, severity=severity)

    def _channel_sequence(self, primary: str, fallback_channels: list[str] | None) -> list[str]:
        sequence = [primary]
        preferred_fallbacks = fallback_channels if fallback_channels is not None else list(self._settings.fallback_channels)
        for channel in preferred_fallbacks:
            if channel in self.CHANNELS and channel not in sequence:
                sequence.append(channel)
        for channel in self.CHANNELS:
            if channel not in sequence:
                sequence.append(channel)
        return sequence

    @staticmethod
    def _default_dispatcher(
        recipient: str,
        message: str,
        attempt: int,
        context: dict[str, str | int | float | bool | None] | None,
    ) -> tuple[bool, str | None]:
        del recipient, message, attempt, context
        return True, None
