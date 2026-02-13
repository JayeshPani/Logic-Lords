"""Preprocessing utilities for LSTM inference."""

from datetime import timedelta

from .config import Settings
from .schemas import RawSensorRecord


class SensorNormalizer:
    """Normalizes raw sensor records to [0, 1] feature vectors."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _scale(value: float, lower: float, upper: float) -> float:
        if upper <= lower:
            return 0.0
        return (value - lower) / (upper - lower)

    def normalize_record(self, record: RawSensorRecord | dict) -> dict[str, float]:
        """Normalize one record using configured feature bounds."""

        payload = record if isinstance(record, RawSensorRecord) else RawSensorRecord.model_validate(record)

        return {
            "strain": self._clamp(
                self._scale(payload.strain_value, self.settings.strain_min, self.settings.strain_max)
            ),
            "vibration": self._clamp(
                self._scale(payload.vibration_rms, self.settings.vibration_min, self.settings.vibration_max)
            ),
            "temperature": self._clamp(
                self._scale(payload.temperature, self.settings.temperature_min, self.settings.temperature_max)
            ),
            "humidity": self._clamp(
                self._scale(payload.humidity, self.settings.humidity_min, self.settings.humidity_max)
            ),
        }


class SequenceBuilder:
    """Builds 48-hour normalized feature windows for model inference."""

    FEATURES = ["strain", "vibration", "temperature", "humidity"]

    def __init__(self, settings: Settings, normalizer: SensorNormalizer):
        self.settings = settings
        self.normalizer = normalizer

    def build_last_48h_sequence(self, history: list[RawSensorRecord] | list[dict]) -> list[list[float]]:
        """Return normalized sequence within the configured time window."""

        normalized_history = [
            point if isinstance(point, RawSensorRecord) else RawSensorRecord.model_validate(point)
            for point in history
        ]
        ordered = sorted(normalized_history, key=lambda point: point.timestamp)
        latest_ts = ordered[-1].timestamp
        cutoff_ts = latest_ts - timedelta(hours=self.settings.history_window_hours)
        windowed = [point for point in ordered if point.timestamp >= cutoff_ts]

        if len(windowed) < self.settings.min_sequence_points:
            raise ValueError(
                f"Need at least {self.settings.min_sequence_points} points in the last "
                f"{self.settings.history_window_hours}h window"
            )

        sequence = []
        for point in windowed:
            normalized = self.normalizer.normalize_record(point)
            sequence.append([normalized[name] for name in self.FEATURES])

        return sequence
